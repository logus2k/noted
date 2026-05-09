import sys
import json

def main():
    try:
        # Read input from stdin
        input_data = sys.stdin.read()
        if not input_data:
            raise ValueError("No input provided.")
        
        data = json.loads(input_data)
    except json.JSONDecodeError:
        sys.stderr.write("Error: Invalid JSON input received.\n")
        sys.exit(1)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(2)

    # Validate required arguments
    if 'name' not in data or not isinstance(data['name'], str):
        sys.stderr.write("Error: Missing or invalid 'name' argument. Please provide a valid name.\n")
        sys.exit(2)

    # Generate greeting
    name = data['name']
    greeting = f"Hello, {name}!"
    
    # Write result to stdout
    result = {"greeting": greeting}
    print(json.dumps(result))

if __name__ == "__main__":
    main()