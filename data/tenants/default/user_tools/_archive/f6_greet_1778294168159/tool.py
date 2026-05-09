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
            sys.stderr.write("Error: Missing or invalid 'name' argument.\n")
            sys.exit(2)

        # Generate greeting
        greeting = f"Hello, {name}! Welcome to the system."
        
        # Write result to stdout
        result = {"greeting": greeting}
        print(json.dumps(result))

    except Exception as e:
        sys.stderr.write(f"An unexpected error occurred: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()