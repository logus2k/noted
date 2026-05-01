"""Serving container configuration from environment variables."""

import os

MLFLOW_TRACKING_URI = os.environ.get('MLFLOW_TRACKING_URI', 'http://mlflow:5000')
MLFLOW_TRACKING_USERNAME = os.environ.get('MLFLOW_TRACKING_USERNAME', '')
MLFLOW_TRACKING_PASSWORD = os.environ.get('MLFLOW_TRACKING_PASSWORD', '')

HOST = os.environ.get('SERVING_HOST', '0.0.0.0')
PORT = int(os.environ.get('SERVING_PORT', '5522'))
