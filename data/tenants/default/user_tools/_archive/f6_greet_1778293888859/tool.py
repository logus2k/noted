import sys
import json

def main():
    try:
        # Read input from stdin
        input_data = sys.stdin.read()
        if not input_data:
            sys.stderr.write("Error: No input received.\n")
            sys.exit(2)
            
        data = json.loads(input_data)
        
        name = data.get("name")
        
        if not name or not isinstance(name, str):
            sys.stderr.write("Error: 'name' field is required and must be a string.\n")
            sys.exit(2)
            
        # Generate greeting
        greeting_message = f"Hello, {name}!"
        
        # Output result to stdout
        result = {"greeting": greeting_message}
        print(json.dumps(result))
        
    except json.JSONDecodeError:
        sys.stderr.write("Error: Invalid JSON input.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"An unexpected error occurred: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()