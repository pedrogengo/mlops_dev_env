import os
from flask import jsonify
import joblib
from google.cloud import storage
import numpy as np
import functions_framework


try:
    artifact_bucket = os.environ['ARTIFACT_BUCKET']
    storage_client = storage.Client()
    bucket = storage_client.bucket(artifact_bucket)
    blob = bucket.blob("prod/model.pkl")
    blob.download_to_filename("/tmp/model.pkl")

    model = joblib.load("/tmp/model.pkl")

except:
    model = None

@functions_framework.http
def handler(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    if model is None:
        return 'You must have a deployed model to execute the function', 404

    request_json = request.get_json(silent=True)

    if request_json and 'input' in request_json:
        inputs = np.array(request_json['input'])
        predicted = model.predict(inputs).tolist()

        out = {"target": predicted}
        return jsonify(out)

    return 'You must send an input data', 400
