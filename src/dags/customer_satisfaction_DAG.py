import io
import uuid
import json
from datetime import datetime, timedelta

from airflow import DAG, AirflowException
from airflow.models import Variable
from airflow import AirflowException

from airflow.operators.python_operator import PythonOperator

import mlflow
from mlflow import log_metric, log_param

from google.cloud import storage
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score


# Trigger with 	{"max_depth": 2, "dataset_path": <YOUR-BUCKET>}

def task_to_fail():
    """
    Dummy function to created a failed task and simulate a manual approval step
    """
    raise AirflowException("Please change this step to success to continue")


def split_train_test(test_ratio=.33, **kwargs):
    """
    Splits a dataset in train and test sets
    """

    run_name = kwargs['ti'].xcom_pull(task_ids='generate_uuid')
    print("run_name:", run_name)

    gcs_path = kwargs['dag_run'].conf.get('dataset_path')

    splitted_path = gcs_path.replace('gs://', '').split('/')
    bucket_name = splitted_path[0]
    source_blob_name = '/'.join(splitted_path[1:])

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    data = blob.download_as_bytes()

    df = pd.read_csv(io.BytesIO(data))

    df_train, df_test = train_test_split(df, test_size=test_ratio)
    artifact_bucket = Variable.get("artifact_bucket")
    print("Artifact bucket:", artifact_bucket)
    bucket = storage_client.bucket(artifact_bucket)
    blob = bucket.blob(f'airflow/{run_name}/train_set.csv').\
        upload_from_string(df_train.to_csv(index=False), 'text/csv')
    blob = bucket.blob(f'airflow/{run_name}/test_set.csv').\
        upload_from_string(df_test.to_csv(index=False), 'text/csv')


def train(**kwargs):
    """"
    Train a Randon Forest Model logging params and metrics to MLFlow
    and saving the model on Google Storage
    """
    run_name = kwargs['ti'].xcom_pull(task_ids='generate_uuid')
    print("run_name:", run_name)

    mlflow.set_tracking_uri('http://mlflow:5000')
    mlflow.sklearn.autolog()
    experiment_id = mlflow.set_experiment("customer_satisfaction").experiment_id

    storage_client = storage.Client()
    artifact_bucket = Variable.get("artifact_bucket")
    bucket = storage_client.bucket(artifact_bucket)
    blob = bucket.blob(f'airflow/{run_name}/train_set.csv')
    data = blob.download_as_bytes()
    df_train = pd.read_csv(io.BytesIO(data))

    blob = bucket.blob(f'airflow/{run_name}/test_set.csv')
    data = blob.download_as_bytes()
    df_test = pd.read_csv(io.BytesIO(data))

    with mlflow.start_run(experiment_id=experiment_id) as run:
        X_train = df_train.drop(columns=['TARGET'])
        y_train = df_train['TARGET']

        X_test = df_test.drop(columns=['TARGET'])
        y_test = df_test['TARGET']

        max_depth = kwargs['dag_run'].conf.get('max_depth')

        rf = RandomForestClassifier(max_depth=max_depth)
        log_param("Model", "RandomForestClassifier")
        log_param("max_depth", max_depth)

        rf.fit(X_train, y_train)

        predicted_y = rf.predict(X_test)

        acc = accuracy_score(y_test, predicted_y)
        log_metric("Accuracy", acc)
    
    return json.dumps({"run_id": run.info.run_id, "experiment_id": experiment_id})


def deploy_to_prod(**kwargs):
    """
    Overwrites or create a model inside bucket/prod to be used by cloud functions
    """
    mlflow_data = json.loads(kwargs['ti'].xcom_pull(task_ids='train_random_forest'))
    artifact_bucket = Variable.get("artifact_bucket")

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(artifact_bucket)
    source_blob = bucket.blob(f"{mlflow_data['experiment_id']}/{mlflow_data['run_id']}/artifacts/model/model.pkl")

    _ = bucket.copy_blob(
        source_blob, bucket, "prod/model.pkl")

    print("Deployed")

# Default settings applied to all tasks
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

with DAG(start_date=datetime(2022, 11, 15),
         dag_id='customer_satisfaction',
         schedule_interval=None,
         default_args=default_args,
         catchup=False
         ) as dag:

    opr_generate_uuid = PythonOperator(
        dag=dag,
        task_id='generate_uuid',
        python_callable=lambda: str(uuid.uuid4())
    )

    opr_split_train_test = PythonOperator(
        dag=dag,
        task_id = 'split_train_test',
        python_callable=split_train_test,
        provide_context=True,
    )

    opr_train_random_forest = PythonOperator(
        dag=dag,
        task_id = 'train_random_forest',
        python_callable=train,
        provide_context=True,
    )

    opr_manual_model_approval = PythonOperator(
        dag=dag,
        task_id="approve_model_to_prod",
        python_callable=task_to_fail,
        retries=1
    )

    opr_deploy_to_prod = PythonOperator(
        dag=dag,
        task_id="deploy_to_prod",
        python_callable=deploy_to_prod,
        provide_context=True
    )


    opr_generate_uuid >> opr_split_train_test >> opr_train_random_forest >> opr_manual_model_approval >> opr_deploy_to_prod
