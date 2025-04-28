import os
import socket
import json
import time
import argparse # Import argparse

# --- Configuration ---
# LOG_FOLDER_PATH is now handled by command-line arguments
LOGSTASH_HOST = "localhost"
LOGSTASH_PORT = 50000
RECONNECT_DELAY_SECONDS = 5
# --- End Configuration ---

def log_parser(line):
    """
    Parses a single log line.
    Initially, just wraps the line in a 'raw_content' field.
    Modify this function later to add your business logic.
    """
    # Remove leading/trailing whitespace
    stripped_line = line.strip()
    if stripped_line: # Avoid sending empty lines
        return {"raw_content": stripped_line}
    else:
        return None # Indicate line should be skipped

def send_to_logstash(host, port, data_list):
    """Sends a list of JSON-serializable data objects to Logstash over TCP."""
    if not data_list:
        print("No data to send.")
        return True # Nothing to send

    try:
        # Establish connection outside the loop for efficiency if sending many items
        with socket.create_connection((host, port), timeout=10) as sock:
            print(f"\nConnected to Logstash at {host}:{port}. Sending data...")
            total_to_send = len(data_list)
            sent_count = 0
            batch_size = 100 # Send in batches for potential efficiency/reduced overhead
            
            for i in range(0, total_to_send, batch_size):
                batch = data_list[i:i + batch_size]
                batch_str = ""
                for data in batch:
                    try:
                        # Convert dict to JSON string and add newline
                        json_string = json.dumps(data) + '\n'
                        batch_str += json_string
                    except (TypeError, OverflowError) as json_err:
                        print(f"\nError serializing data: {data}. Skipping item. Error: {json_err}")
                        
                if not batch_str: # Skip empty batches if serialization failed for all items
                    continue
                    
                try:
                    # Encode the entire batch to bytes for sending
                    sock.sendall(batch_str.encode('utf-8'))
                    sent_count += len(batch)
                    # Simple progress for sending (optional, can be noisy)
                    # print(f"Sending to Logstash: {sent_count}/{total_to_send} lines sent...", end='\r')
                except socket.error as send_err:
                     print(f"\nSocket error during send: {send_err}")
                     # Attempt to resend might be complex here, easier to drop and reconnect later
                     return False # Indicate failure
                     
            print(f"\nSuccessfully sent {sent_count} log entries.      ") # Spaces to overwrite progress
            return True # Indicate success
            
    except socket.error as conn_err:
        print(f"\nFailed to connect or send to Logstash ({host}:{port}): {conn_err}")
        return False # Indicate failure
    except Exception as e:
        print(f"\nAn unexpected error occurred during sending: {e}")
        return False

def process_log_file(filepath):
    """Reads a file, parses lines, and prepares data for sending."""
    processed_data = []
    # print(f"Processing file: {filepath}") # Keep this if verbose file-by-file output is desired
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                parsed_log = log_parser(line)
                if parsed_log: # Only add if parser returned data
                    processed_data.append(parsed_log)
    except FileNotFoundError:
        print(f"\nError: File not found during processing: {filepath}") # Add newline for clarity with progress indicator
    except Exception as e:
        print(f"\nError reading file {filepath}: {e}") # Add newline
    return processed_data

def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Read log files recursively and send them to Logstash.")
    parser.add_argument(
        "-f", "--log-folder",
        required=True,
        help="Path to the root folder containing log files."
    )
    parser.add_argument(
        "--host",
        default=LOGSTASH_HOST,
        help=f"Logstash host address (default: {LOGSTASH_HOST})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=LOGSTASH_PORT,
        help=f"Logstash TCP input port (default: {LOGSTASH_PORT})"
    )
    args = parser.parse_args()

    log_folder_path = args.log_folder
    logstash_host = args.host
    logstash_port = args.port
    # --- End Argument Parsing ---


    if not os.path.isdir(log_folder_path):
        print(f"Error: Log folder not found: {log_folder_path}")
        print("Please provide a valid directory path.")
        return

    print(f"Scanning for log files in: {log_folder_path} (including subfolders)...")
    all_files = []
    # Use os.walk to find files recursively
    for dirpath, _, filenames in os.walk(log_folder_path):
        for filename in filenames:
            # Construct full path
            filepath = os.path.join(dirpath, filename)
            # Optional: Add checks here if you only want certain file extensions (e.g., .log)
            # if filename.lower().endswith('.log'):
            all_files.append(filepath)

    if not all_files:
        print(f"No files found in {log_folder_path} or its subfolders.")
        return

    total_files = len(all_files)
    print(f"Found {total_files} files. Processing...")

    data_to_send = []
    processed_count = 0

    # --- Processing Loop with Progress ---
    for log_file in all_files:
        data_to_send.extend(process_log_file(log_file))
        processed_count += 1
        # Calculate percentage and display progress
        percent_done = int((processed_count / total_files) * 100)
        # Use \r to return cursor to the beginning of the line
        # Add spaces at the end to overwrite previous longer messages
        print(f"Processing files: {processed_count}/{total_files} ({percent_done}%) completed... ", end='\r')

    # Print a newline to move past the progress indicator after the loop
    print("\nFile processing complete.")
    # --- End Processing Loop ---


    if not data_to_send:
        print("No processable log lines found in any file.")
        return

    print(f"\nPrepared {len(data_to_send)} total log entries to send.")

    # Attempt to send data with retry logic
    success = False
    while not success:
         success = send_to_logstash(logstash_host, logstash_port, data_to_send)
         if not success:
             print(f"Will retry sending in {RECONNECT_DELAY_SECONDS} seconds...")
             time.sleep(RECONNECT_DELAY_SECONDS)

    print("\nLog sending process complete.")


if __name__ == "__main__":
    main()