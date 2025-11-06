import json
import sys
from typing import Dict, Any, List, Tuple

class DuplicateKeyError(json.JSONDecodeError):
    """Custom exception for reporting duplicate keys found during JSON parsing."""
    pass

def raise_on_duplicate_keys(ordered_pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """
    A custom hook for json.load() that checks for duplicate keys 
    in the list of (key, value) pairs before creating the final dictionary.
    """
    seen_keys = {}
    
    # Iterate through the pairs in the order they appeared in the file
    for key, value in ordered_pairs:
        if key in seen_keys:
            # Raise a custom error immediately upon finding the duplicate
            raise DuplicateKeyError(
                f"Duplicate key '{key}' found.", 
                doc='(Not available for this parsing method)', 
                pos=0  # Position is hard to calculate accurately here, 0 is a placeholder
            )
        seen_keys[key] = value
        
    # Return the processed dictionary to complete the loading process
    return seen_keys

def load_json_and_check_duplicates(file_path: str) -> Dict[str, Any]:
    """
    Loads a JSON file using the custom hook to check for duplicate keys.
    
    Returns: The loaded dictionary if successful.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Use object_pairs_hook to trigger the custom function before dict creation
            data = json.load(f, object_pairs_hook=raise_on_duplicate_keys)
            
        return data
        
    except FileNotFoundError:
        print(f" Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
        
    except DuplicateKeyError as e:
        # Catch the specific error raised by the custom hook
        print(f" JSON Validation Failed! **Duplicate Key Error** in '{file_path}'.", file=sys.stderr)
        print(f"  **Error:** {e.msg}", file=sys.stderr)
        sys.exit(1)
        
    except json.JSONDecodeError as e:
        # Catch general syntax errors (e.g., missing comma, invalid token)
        print(f" JSON Validation Failed! **Syntax Error** in '{file_path}'.", file=sys.stderr)
        print(f"  **Error Message:** {e.msg}", file=sys.stderr)
        print(f"  **Location:** Line {e.lineno}, Column {e.colno}", file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        print(f" An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


# --- Example Usage (How to integrate this into your main script) ---
if __name__ == "__main__":
    
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <path_to_json_file>", file=sys.stderr)
        sys.exit(1)
        
    target_file = sys.argv[1]
    
    print(f"Attempting to load and validate: **{target_file}**")
    
    # Run the validation
    loaded_data = load_json_and_check_duplicates(target_file)
    
    print(f" Success: JSON is valid and contains no duplicate keys. Total keys: {len(loaded_data)}")

    # You can now safely use the `loaded_data` dictionary in your script.
