import os.path
import re
import socket
import threading
import cv2
import json
from datetime import datetime
from utils import create_recursive_dir, capture_roi, save_video, read_stream
from collections import deque, defaultdict
import yaml
import keyboard

# Open the YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

file_path = "data.json"
# # Define the RTSP stream data for each terminal
# rtsp_streams = {
#     # "73": {"stream": 'rtsp://admin:HikVision1@10.16.60.93:554/Streaming/Channels/103', "ip_address": "10.16.20.193"},
#     # "74": {"stream": 'rtsp://admin:HikVision1@10.16.60.94:554/Streaming/Channels/103', "ip_address": "10.16.20.194"},
#     # "75": {"stream": 'rtsp://admin:HikVision1@10.16.60.95:554/Streaming/Channels/103', "ip_address": "10.16.20.195"},
#     "76": {
#         "stream": "rtsp://admin:HikVision1@10.16.60.96:554/Streaming/Channels/103",
#         "ip_address": "10.16.20.196",
#     },
#     # "77": {"stream": r'rtsp://admin:HikVision1@10.16.60.97:554/Streaming/Channels/103', "ip_address": "10.16.20.197"},
#     # "78": {"stream": 'rtsp://admin:HikVision1@10.16.60.98:554/Streaming/Channels/103', "ip_address": "10.16.20.198"},
#     # "79": {"stream": 'rtsp://admin:HikVision1@10.16.60.99:554/Streaming/Channels/103', "ip_address": "10.16.20.199"},
#     # "80": {"stream": 'rtsp://admin:HikVision1@10.16.60.100:554/Streaming/Channels/103', "ip_address": "10.16.20.200"}
# }


sno_counters = {
    terminal: 0 for terminal in config["input_rtsp_streams"]
}  # Dictionary to store qqindividual counters for each terminal


# Setting output path
current_date = datetime.now().strftime("%Y-%m-%d")
frame_save_path = os.path.join("Outputs", current_date)
all_terminal_data = {}
for terminal in config["input_rtsp_streams"]:
    all_terminal_data[terminal] = None


def extract_event_data(received_data):
    # Regular expressions to extract the required values
    terminal_regex = r'Terminal="(\d+)"'
    till_num_regex = r'<Param Name="Till Num" Value="(\d+)" />'
    item_code_regex = r'<Param Name="Item Code" Value="(\d+)" />'
    description_regex = r'<Param Name="Description" Value="([^"]+)" />'
    quantity_regex = r'<Param Name="Quantity" Value="(\d+)" />'
    # sales_amount_regex = r'<Param Name="Sales Amount" Value="([^"]+)" />'
    grand_total_regex = r'<Param Name="Grand Total" Value="([^"]+)" />'
    #

    event_dict = {}

    # Extract Terminal value
    terminal_match = re.search(terminal_regex, received_data)
    if terminal_match:
        event_dict["Terminal"] = terminal_match.group(1)

    # Extract other values using regular expressions
    till_num_match = re.search(till_num_regex, received_data)
    if till_num_match:
        event_dict["Till Num"] = till_num_match.group(1)

    item_code_match = re.search(item_code_regex, received_data)
    if item_code_match:
        event_dict["Item Code"] = item_code_match.group(1)
    #
    description_match = re.search(description_regex, received_data)
    if description_match:
        event_dict["Description"] = description_match.group(1)
    #
    # quantity_match = re.search(quantity_regex, received_data)
    # if quantity_match:
    #     event_dict['Quantity'] = quantity_match.group(1)
    #
    # sales_amount_match = re.search(sales_amount_regex, received_data)
    # if sales_amount_match:
    #     event_dict['Sales Amount'] = sales_amount_match.group(1)

    grand_total_match = re.search(grand_total_regex, received_data)
    if grand_total_match:
        event_dict["Grand Total"] = grand_total_match.group(1)

    return event_dict


def handle_client(client_socket, client_address, terminal_id):
    global all_terminal_data

    try:
        print(f"Connected to client: {client_address}")
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            received_data = data.decode()
            # print(received_data)
            event_data = extract_event_data(received_data)
            all_terminal_data[terminal_id] = event_data
            # print(event_data)

    except Exception as e:
        print(received_data)
        print(f"Error handling client {client_address}: {e}")
    finally:
        client_socket.close()
        print(f"Connection closed with client: {client_address}")


def start_socket_server(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(8)
    print(f"Server listening on {host}:{port}")

    while True:
        client_socket, client_address = server_socket.accept()
        stream_info = None
        for terminal, info in rtsp_streams.items():
            if client_address[0] == info["ip_address"]:
                stream_info = info
                break

        if stream_info:
            terminal = next(
                (term for term, info in rtsp_streams.items() if info == stream_info),
                None,
            )
            if terminal:
                print("Listening for", terminal)
                client_thread = threading.Thread(
                    target=handle_client, args=(client_socket, client_address, terminal)
                )
                client_thread.start()
        else:
            client_socket.close()


def process_video(stream_url, roi, terminal_id):
    resize_factor = 1
    # URL of the video stream
    print(stream_url)
    # Open the stream
    cap = cv2.VideoCapture(stream_url)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    print("Fps", fps)
    latest_transaction_num = 0

    # Check if the stream is opened successfully
    if not cap.isOpened():
        print("Error: Could not open stream.")
        exit()

    roi_x1 = int(roi[0])
    roi_x2 = int(roi[0] + roi[2])
    roi_y1 = int(roi[1])
    roi_y2 = int(roi[1] + roi[3])
    ret, frame = cap.read()
    prev_crop = frame[roi_y1:roi_y2, roi_x1:roi_x2].copy()

    noise_count = 0
    global all_terminal_data

    patience = 0
    PATIENCE_THRESH = 5
    ITEM_CONFIRM_THRESH = 20
    frames_list = []
    item_count = 0
    i = 0

    # Read and display frames from the stream
    while True:
        ret, frame = cap.read()

        # if not ret:
        #     print("Error: Could not read frame.")
        #     continue
        if frame is not  None:
            # --- Logic for item detection ---

            frame = cv2.resize(frame, (0, 0), fx=1 / resize_factor, fy=1 / resize_factor)
            crop = frame[roi_y1:roi_y2, roi_x1:roi_x2].copy()
            diff = cv2.absdiff(prev_crop, crop)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 20, 255, cv2.THRESH_BINARY)
            i = i + 1
            # Calculating noise
            white_pixels = len(thresh[thresh >= 50])
            noise = round((white_pixels / thresh.size * 100), 2)

            if all_terminal_data[terminal_id] is not None:
                latest_transaction_num = all_terminal_data[terminal_id].get("Till Num")
            if noise >= 25:
                patience = 0
                frames_list.append(frame)
                noise_count = noise_count + 1
            else:
                # Wait for few frames
                patience = patience + 1
                if patience > PATIENCE_THRESH:
                    if noise_count > ITEM_CONFIRM_THRESH:
                        item_count = item_count + 1
                        # print('Item count:', item_count)
                        # print('Noise count:', noise_count)
                        if all_terminal_data[terminal_id] is None:
                            try:
                                print("Item was not scanned properly")
                                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

                                # Save the image with timestamp as filename
                                filename = timestamp + ".mp4"
                                save_video_path = os.path.join(
                                    frame_save_path,
                                    str(terminal_id),
                                    str(latest_transaction_num),
                                )
                                create_recursive_dir(save_video_path)
                                save_video(
                                    os.path.join(
                                        save_video_path,
                                        filename,
                                    ),
                                    frames_list,
                                )
                            except Exception as e:
                                print(e)
                        else:
                            print("Item match with Terminal data")
                    all_terminal_data[terminal_id] = None
                    noise_count = 0
                    frames_list = []

            if i % 30 == 0:
                prev_crop = frame[roi_y1:roi_y2, roi_x1:roi_x2]

        # --- Logic for item detection end ---

        cv2.imshow(f"Crop-{terminal_id}", thresh)
        # cv2.imshow(f"Stream-{terminal_id}", frame)
        t_data = all_terminal_data[terminal_id]
        if t_data is not None and "Grand Total" in t_data:
            item_count = 0

        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Release the capture object and close any open windows
    cap.release()
    cv2.destroyAllWindows()


# Press the green button in the gutter to run the script.
if __name__ == "__main__":
    t1 = threading.Thread(
        target=start_socket_server,
        args=(config["connection"]["host"], config["connection"]["port"]),
    )
    t1.daemon = True
    t1.start()

    rtsp_streams = config["input_rtsp_streams"]
    for terminal_id in rtsp_streams:
        video_source = stream_url = rtsp_streams[terminal_id]["stream"]
        roi = capture_roi(video_source)
        t = threading.Thread(
            target=process_video, args=(video_source, roi, terminal_id)
        )
        t.daemon = True
        t.start()
        # process_video(video_source, roi, terminal_id=terminal_id)
    keyboard.wait('q')
    # while True:
    #     if keyboard.is_pressed('q'):  # If the 'q' key is pressed
    #         print("Exiting the program.")
