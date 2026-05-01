"""Prediction handler - parses input, runs inference, formats output.

Bridges the gap between JSON request data and the model's expected
input format (DataFrame, ndarray, tensor).
"""

import logging
import json
import numpy as np

logger = logging.getLogger(__name__)


def run_prediction(model, input_data: dict, schema: dict) -> dict:
    """Run prediction on the loaded model.

    Args:
        model: Loaded mlflow.pyfunc model
        input_data: Raw input from the API request
        schema: Schema from schema_builder (for format hints)

    Returns:
        {"prediction": ..., "format": "scalar"|"ndarray"|"dataframe", "shape": [...]}
    """
    input_format = schema.get('input_format', 'dataframe')
    parsed_input = _parse_input(input_data, input_format, schema.get('inputs', []))

    # Run inference
    try:
        if isinstance(parsed_input, np.ndarray) and parsed_input.ndim >= 3:
            # 3D+ tensor: prefer the unwrapped native model (Keras/PyTorch can
            # accept the ndarray directly; pyfunc's DataFrame coercion rejects
            # >=3D shapes). Fall back to the pyfunc wrapper itself for pure
            # PythonModel subclasses that don't expose `get_raw_model`.
            try:
                unwrapped = _get_unwrapped_model(model)
                raw_output = unwrapped.predict(parsed_input)
            except (ValueError, NotImplementedError):
                # Custom pyfunc (e.g. mlflow.pyfunc.PythonModel subclass) -
                # call its predict() directly; the pyfunc wrapper forwards to
                # the PythonModel's predict(context, input).
                raw_output = model.predict(parsed_input)
            if hasattr(raw_output, 'numpy'):
                raw_output = raw_output.numpy()
        else:
            raw_output = model.predict(parsed_input)
    except Exception as e:
        raise ValueError(f"Prediction failed: {e}")

    return _format_output(raw_output, schema)


def _get_unwrapped_model(pyfunc_model):
    """Extract the native model from an MLflow pyfunc wrapper."""
    # get_raw_model() is the official MLflow API
    if hasattr(pyfunc_model, 'get_raw_model'):
        return pyfunc_model.get_raw_model()
    # Fallback: try known wrapper attributes
    if hasattr(pyfunc_model, '_model_impl'):
        impl = pyfunc_model._model_impl
        for attr in ('keras_model', 'model', 'spark_model'):
            if hasattr(impl, attr):
                return getattr(impl, attr)
    raise ValueError("Unable to retrieve base model object from pyfunc")


def _parse_input(input_data, input_format: str, input_fields: list):
    """Parse JSON input into the format expected by the model."""
    import pandas as pd

    # If input is already a list/array, use it directly
    if isinstance(input_data, (list, tuple)):
        arr = np.array(input_data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.ndim >= 3:
            return arr
        return pd.DataFrame(arr)

    if input_format == 'tensor':
        # Expect {"data": [[...], ...]} or {"data": [...]}
        data = input_data.get('data')
        if data is None:
            # Try to build from named fields
            data = input_data.get('values', input_data.get('input'))
        if data is None:
            raise ValueError("Tensor input requires 'data' field with array values")
        arr = np.array(data, dtype=np.float32)
        # Add batch dimension if needed
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        # For 3D+ tensors, return raw ndarray (pyfunc can't handle 3D)
        if arr.ndim >= 3:
            return arr
        return pd.DataFrame(arr)

    # DataFrame format
    if 'columns' in input_data and 'data' in input_data:
        # Explicit columnar format: {"columns": [...], "data": [[...]]}
        return pd.DataFrame(input_data['data'], columns=input_data['columns'])

    if input_fields:
        # Build DataFrame from named fields
        row = {}
        for field in input_fields:
            name = field['name']
            if name in input_data:
                val = input_data[name]
                if isinstance(val, list):
                    # Array field - each element becomes a row
                    return pd.DataFrame({name: val for name, val in input_data.items()
                                        if name in [f['name'] for f in input_fields]})
                row[name] = val
        if row:
            return pd.DataFrame([row])

    # Fallback: treat entire dict as a single-row DataFrame
    return pd.DataFrame([input_data])


def _format_output(raw_output, schema: dict) -> dict:
    """Format model output for JSON response."""
    output_format = schema.get('output_format', 'unknown')
    visualization = schema.get('output_visualization', 'value')

    # Convert to serializable format
    if hasattr(raw_output, 'values'):
        # pandas DataFrame or Series
        if hasattr(raw_output, 'columns'):
            values = raw_output.values.tolist()
            columns = raw_output.columns.tolist()
            if len(values) == 1:
                # Single prediction
                if len(columns) == 1:
                    return {
                        'prediction': values[0][0],
                        'format': 'scalar',
                        'visualization': 'value',
                    }
                return {
                    'prediction': dict(zip(columns, values[0])),
                    'format': 'dataframe',
                    'columns': columns,
                    'visualization': visualization,
                }
            return {
                'prediction': values,
                'format': 'dataframe',
                'columns': columns,
                'visualization': 'table',
            }
        else:
            values = raw_output.values.tolist()
            return {
                'prediction': values,
                'format': 'ndarray',
                'shape': list(raw_output.shape),
                'visualization': visualization,
            }

    if isinstance(raw_output, np.ndarray):
        # Squeeze batch dimension for single predictions (e.g., (1, 24) -> (24,))
        if raw_output.ndim == 2 and raw_output.shape[0] == 1:
            raw_output = raw_output.squeeze(0)
        values = raw_output.tolist()
        if raw_output.ndim == 0:
            return {'prediction': values, 'format': 'scalar', 'visualization': 'value'}
        if raw_output.ndim == 1 and len(values) == 1:
            return {'prediction': values[0], 'format': 'scalar', 'visualization': 'value'}
        if raw_output.ndim == 1:
            return {
                'prediction': values,
                'format': 'ndarray',
                'shape': list(raw_output.shape),
                'visualization': 'line_chart' if len(values) > 3 else 'value',
            }
        return {
            'prediction': values,
            'format': 'ndarray',
            'shape': list(raw_output.shape),
            'visualization': 'table',
        }

    if isinstance(raw_output, (list, tuple)):
        return {
            'prediction': list(raw_output),
            'format': 'ndarray',
            'shape': [len(raw_output)],
            'visualization': 'line_chart' if len(raw_output) > 3 else 'value',
        }

    # Scalar
    if isinstance(raw_output, (int, float)):
        return {'prediction': raw_output, 'format': 'scalar', 'visualization': 'value'}

    # Fallback
    return {'prediction': str(raw_output), 'format': 'string', 'visualization': 'value'}
