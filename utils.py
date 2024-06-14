import os
import cv2


def create_recursive_dir(path):
    """Creates a recursive directory path if it does not already exist."""
    try:
        # Use the exist_ok=True parameter to avoid raising an error if the directory already exists
        os.makedirs(path, exist_ok=True)
    except OSError as error:
        print(f"Creation of the directory {path} failed due to {error}")


def capture_roi(video_source, resize_factor=1):

    cap = cv2.VideoCapture(video_source)
    ret, frame = cap.read()
    cap.release()

    frame = cv2.resize(frame, (0, 0), fx=1 / resize_factor, fy=1 / resize_factor)

    r = cv2.selectROI("a", frame)
    resized_r = [frm * resize_factor for frm in r]
    cv2.destroyWindow("a")
    return tuple(resized_r)


def save_video(
    output_video_path,
    frames_list,
):
    height, width, _ = frames_list[0].shape

    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(
        *"MP4V"
    )  # You can use other codecs as well, e.g., 'XVID', 'MJPG'
    out = cv2.VideoWriter(
        output_video_path, fourcc, 25, (width, height)
    )  # Adjust the frame rate (here 30) as needed

    # Write each frame to the video
    for frame in frames_list:
        out.write(frame)

    # Release the VideoWriter object
    out.release()

    print("Video saved successfully.")


import sys


def read_stream(stream, cam_id):

    # Initialize video capture from the first webcam
    cap = cv2.VideoCapture(stream)

    if not cap.isOpened():
        print("Error: Could not open video device.")
        sys.exit()

    # Set properties, optional
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    try:
        while True:
            # Read a new frame
            ret, frame = cap.read()
            if not ret:
                print("Failed to read frame.")
                break

            # Display the frame
            cv2.imshow(str(cam_id), frame)

            # Break the loop when 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        print("Stream stopped by user.")

    finally:
        # Release the capture and close any OpenCV windows
        cap.release()
        cv2.destroyAllWindows()
