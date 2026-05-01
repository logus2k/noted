"""Build rich input/output metadata from MLflow model signatures.

Produces structured schema descriptions that the frontend uses to
dynamically generate input forms and output renderers.
"""

import logging

logger = logging.getLogger(__name__)


def build_schema(model_info: dict, model=None) -> dict:
    """Build input/output schema from MLflow model metadata.

    Args:
        model_info: Dict with 'signature', 'flavors', 'metadata' from MLflow
        model: The loaded pyfunc model (optional, for additional introspection)

    Returns:
        {
            "inputs": [...],
            "outputs": [...],
            "input_format": "dataframe" | "tensor",
            "input_shape": [rows, cols] | None,
            "output_format": "ndarray" | "dataframe" | "scalar" | "class_probabilities",
            "output_visualization": "line_chart" | "bar_chart" | "table" | "value",
            "class_labels": [...] | None,
            "example_input": {...} | None,
        }
    """
    signature = model_info.get('signature')
    inputs_schema = _parse_inputs(signature)
    outputs_schema = _parse_outputs(signature)
    input_format = _detect_input_format(signature, model_info)
    output_format, visualization = _detect_output_format(outputs_schema, model_info)

    # Try to extract example input from model metadata
    example_input = model_info.get('example_input')

    # Input shape hint - prefer signature shape, then model introspection
    input_shape = None
    if inputs_schema and inputs_schema[0].get('type') == 'tensor' and inputs_schema[0].get('shape'):
        input_shape = inputs_schema[0]['shape']
        # Replace -1 (batch dim) with 1
        input_shape = [s if s != -1 else 1 for s in input_shape]
    elif inputs_schema:
        cols = len(inputs_schema)
        input_shape = [1, cols]  # Default: single-row input
    elif model is not None:
        # Try to infer shape from the loaded model (Keras, PyTorch, etc.)
        try:
            raw = model.get_raw_model() if hasattr(model, 'get_raw_model') else None
            if raw is None and hasattr(model, '_model_impl'):
                for attr in ('keras_model', 'model'):
                    if hasattr(model._model_impl, attr):
                        raw = getattr(model._model_impl, attr)
                        break
            if raw is not None:
                if hasattr(raw, 'input_shape'):
                    # Keras model
                    shape = raw.input_shape
                    if isinstance(shape, tuple) and len(shape) >= 2:
                        input_shape = [s if s is not None else 1 for s in shape]
                elif hasattr(raw, 'input_size'):
                    input_shape = [1, raw.input_size]
        except Exception:
            pass

    example_request_body = _build_example_request_body(
        input_format, input_shape, inputs_schema
    )

    return {
        'inputs': inputs_schema,
        'outputs': outputs_schema,
        'input_format': input_format,
        'input_shape': input_shape,
        'output_format': output_format,
        'output_visualization': visualization,
        'class_labels': model_info.get('class_labels'),
        'example_input': example_input,
        'example_request_body': example_request_body,
    }


def _build_example_request_body(input_format: str, input_shape, inputs_schema: list) -> dict:
    """Generate a ready-to-POST example body for /predict based on the model's
    input format. The body is always wrapped in {"data": ...} so both internal
    callers (noted-serving's /predict) and external callers (noted's
    /api/serving/predict proxy) consume the same payload shape.

    Mirrors the browser-side builder in ExplorerPanel._buildExampleRequestBody
    so the frontend example matches what the model sees via the assistant's
    get_serving_schema tool.
    """
    if input_format == 'tensor':
        shape = list(input_shape) if input_shape else [1]
        # Replace None / -1 / 0 with 1 so the zeros-tensor has a concrete shape.
        shape = [s if isinstance(s, int) and s > 0 else 1 for s in shape]

        def _zeros(dims):
            if not dims:
                return 0.0
            return [_zeros(dims[1:]) for _ in range(int(dims[0]))]

        return {'data': _zeros(shape)}

    if input_format == 'columnar':
        cols = [i.get('name') or f'col_{idx}' for idx, i in enumerate(inputs_schema or [])]
        if not cols:
            cols = ['col_0']
        return {'data': {'columns': cols, 'data': [[0.0 for _ in cols]]}}

    # Default: single-row dataframe input
    row: dict = {}
    for idx, inp in enumerate(inputs_schema or []):
        name = inp.get('name') or f'col_{idx}'
        inp_type = inp.get('type', 'float')
        if inp_type == 'integer':
            row[name] = 0
        elif inp_type in ('boolean', 'bool'):
            row[name] = False
        elif inp_type in ('string', 'str'):
            row[name] = ''
        else:
            row[name] = 0.0
    if not row:
        row = {'col_0': 0.0}
    return {'data': row}


def _parse_inputs(signature) -> list[dict]:
    """Parse MLflow signature inputs into structured field descriptions."""
    if not signature or not hasattr(signature, 'inputs'):
        return []

    inputs = signature.inputs
    if inputs is None:
        return []

    fields = []
    try:
        # TensorSpec-based signature (check FIRST - input_names exists but returns indices for tensors)
        if hasattr(inputs, 'is_tensor_spec') and inputs.is_tensor_spec():
            for i, spec in enumerate(inputs.inputs):
                shape = list(spec.shape) if hasattr(spec, 'shape') else []
                dtype = str(spec.type) if hasattr(spec, 'type') else 'float32'
                fields.append({
                    'name': spec.name if hasattr(spec, 'name') and spec.name else f'input_{i}',
                    'type': 'tensor',
                    'dtype': dtype,
                    'shape': shape,
                    'description': f'Tensor input, shape: {tuple(shape)}, dtype: {dtype}',
                })
        # ColSpec-based signature (dataframe input)
        elif hasattr(inputs, 'has_input_names') and inputs.has_input_names():
            names = inputs.input_names()
            for i, name in enumerate(names):
                col = inputs.inputs[i] if hasattr(inputs, 'inputs') else None
                dtype = str(col.type) if col and hasattr(col, 'type') else 'float'
                fields.append({
                    'name': name or f'input_{i}',
                    'type': _normalize_type(dtype),
                    'description': '',
                })
        elif hasattr(inputs, 'to_dict'):
            for col in inputs.to_dict():
                fields.append({
                    'name': col.get('name', ''),
                    'type': _normalize_type(col.get('type', 'float')),
                    'description': '',
                })
        elif hasattr(inputs, 'numpy_shape'):
            shape = inputs.numpy_shape()
            fields.append({
                'name': 'input',
                'type': 'tensor',
                'shape': list(shape) if shape else [],
                'description': f'Tensor input, shape: {shape}',
            })
    except Exception as e:
        logger.debug("Failed to parse input signature: %s", e)

    return fields


def _parse_outputs(signature) -> list[dict]:
    """Parse MLflow signature outputs into structured field descriptions."""
    if not signature or not hasattr(signature, 'outputs'):
        return []

    outputs = signature.outputs
    if outputs is None:
        return []

    fields = []
    try:
        if hasattr(outputs, 'input_names') and callable(outputs.input_names):
            names = outputs.input_names()
            for i, name in enumerate(names):
                col = outputs.inputs[i] if hasattr(outputs, 'inputs') else None
                dtype = str(col.type) if col and hasattr(col, 'type') else 'float'
                fields.append({
                    'name': name or f'output_{i}',
                    'type': _normalize_type(dtype),
                    'description': '',
                })
        elif hasattr(outputs, 'to_dict'):
            for col in outputs.to_dict():
                fields.append({
                    'name': col.get('name', ''),
                    'type': _normalize_type(col.get('type', 'float')),
                    'description': '',
                })
        elif hasattr(outputs, 'is_tensor_spec') and outputs.is_tensor_spec():
            for i, spec in enumerate(outputs.inputs):
                shape = list(spec.shape) if hasattr(spec, 'shape') else []
                dtype = str(spec.type) if hasattr(spec, 'type') else 'float64'
                fields.append({
                    'name': spec.name if hasattr(spec, 'name') and spec.name else 'prediction',
                    'type': 'tensor',
                    'dtype': dtype,
                    'shape': shape,
                    'description': f'Tensor output, shape: {tuple(shape)}, dtype: {dtype}',
                })
        elif hasattr(outputs, 'numpy_shape'):
            shape = outputs.numpy_shape()
            fields.append({
                'name': 'prediction',
                'type': 'tensor',
                'shape': list(shape) if shape else [],
                'description': f'Tensor output, shape: {shape}',
            })
    except Exception as e:
        logger.debug("Failed to parse output signature: %s", e)

    return fields


def _detect_input_format(signature, model_info: dict) -> str:
    """Detect whether the model expects dataframe or tensor input."""
    flavors = model_info.get('flavors', {})
    if 'sklearn' in str(flavors) or 'lightgbm' in str(flavors) or 'xgboost' in str(flavors):
        return 'dataframe'
    if 'pytorch' in str(flavors) or 'tensorflow' in str(flavors) or 'keras' in str(flavors):
        return 'tensor'
    # Flavor-agnostic fallback: inspect the signature directly. Pyfunc-only
    # models (e.g. custom PythonModel subclasses) carry no framework flavor
    # but DO carry a proper input signature. If it's a TensorSpec-based
    # signature, treat as tensor. This prevents multi-dim tensor inputs
    # from being misrouted through the dataframe parser.
    try:
        if signature is not None and hasattr(signature, 'inputs') and signature.inputs is not None:
            inputs = signature.inputs
            if hasattr(inputs, 'is_tensor_spec') and inputs.is_tensor_spec():
                return 'tensor'
    except Exception:
        pass
    return 'dataframe'


def _detect_output_format(outputs: list[dict], model_info: dict) -> tuple[str, str]:
    """Detect output format and suggest visualization type."""
    if not outputs:
        return 'unknown', 'value'

    # Single scalar output
    if len(outputs) == 1 and outputs[0].get('type') in ('float', 'double', 'int', 'long'):
        return 'scalar', 'value'

    # Tensor output with shape
    if len(outputs) == 1 and outputs[0].get('type') == 'tensor':
        shape = outputs[0].get('shape', [])
        if len(shape) == 1 and shape[0] > 1:
            return 'ndarray', 'line_chart'
        return 'ndarray', 'table'

    # Multiple named outputs - likely class probabilities or multi-output
    if len(outputs) > 2:
        # Check if names look like classes
        names = [o.get('name', '') for o in outputs]
        if all(n and not n.startswith('output_') for n in names):
            return 'class_probabilities', 'bar_chart'

    return 'dataframe', 'table'


def _normalize_type(dtype: str) -> str:
    """Normalize MLflow type strings to simple type names."""
    dtype = str(dtype).lower()
    if 'float' in dtype or 'double' in dtype:
        return 'float'
    if 'int' in dtype or 'long' in dtype:
        return 'integer'
    if 'bool' in dtype:
        return 'boolean'
    if 'str' in dtype or 'string' in dtype:
        return 'string'
    return dtype
