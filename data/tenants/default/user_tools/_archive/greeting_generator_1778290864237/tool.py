import sys
import json

def main():
    try:
        # Read input from stdin
        input_data = sys.stdin.read()
        if not input_data:
            sys.stderr.write("Error: No input provided.\n")
            sys.exit(2)
            
        try:
            data = json.loads(input_data)
        except json.JSONDecodeError:
            sys.stderr.write("Error: Invalid JSON input.\n")
            sys.exit(2)

        # Validate required arguments
        name = data.get("name")
        if not name or not isinstance(name, str):
            sys.stderr.write("Error: Missing or invalid 'name' argument. Please provide a valid name.\n")
            sys.exit(2)

        # Generate greeting
        greeting = f"Hello, {name}!"
        result = {"greeting": greeting}

        # Write result to stdout
        print(json.dumps(result))

    except Exception as e:
        sys.stderr.write(f"An unexpected error occurred: {e}\n")
        sys.exit(1)