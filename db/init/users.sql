CREATE USER 'mlflow_user'@'%' IDENTIFIED BY 'mlflow_password';
GRANT ALL PRIVILEGES ON *.* TO 'mlflow_user'@'%';

CREATE USER 'airflow_user'@'%' IDENTIFIED BY 'airflow_password';
GRANT ALL PRIVILEGES ON *.* TO 'airflow_user'@'%';