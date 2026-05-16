import cv2
import numpy as np
import time
import joblib
import pymysql
from picamera2 import Picamera2
from ultralytics import YOLO
from tflite_runtime.interpreter import Interpreter
import os
from skimage.feature import graycomatrix, graycoprops

# ================= CONFIG =================
YOLO_MODEL_PATH   = "/home/ama_poultry/ama_cap/best.pt"
TFLITE_MODEL_PATH = "/home/ama_poultry/ama_cap/fusion_model.tflite"

IMG_SIZE            = 320
FRAME_SKIP          = 3
CONF_THRESHOLD      = 0.5
MAX_DET             = 1
PREDICTION_COOLDOWN = 3.0  # seconds between logged predictions

def log(stage, message):
    print(f"[{stage}] {message}")

# ================= LOAD MODELS =================
log("MODEL", "Loading YOLO model")
yolo_model = YOLO(YOLO_MODEL_PATH)
log("MODEL", "YOLO loaded")

interpreter = Interpreter(model_path=TFLITE_MODEL_PATH)
interpreter.allocate_tensors()

input_details  = interpreter.get_input_details()
output_details = interpreter.get_output_details()

hsv_scaler     = joblib.load("hsv_scaler.pkl")
texture_scaler = joblib.load("texture_scaler.pkl")
label_classes  = np.load("label_classes.npy")

print("Classes in order:")
for i, cls in enumerate(label_classes):
    print(f"  {i} -> {cls}")

print(input_details)

# ================= CAMERA SETUP =================
picam2 = Picamera2()

config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"}  # native RGB output
)

picam2.configure(config)
picam2.start()
time.sleep(2)
log("CAMERA", "Camera initialized")

# ================= CREATE SAVE DIR =================
save_dir = "/home/ama_poultry/ama_cap/comb_outputs"
os.makedirs(save_dir, exist_ok=True)

# ================= DATABASE =================
def send_to_db(pred, conf, fps, inference_time, img_path):
    try:
        connection = pymysql.connect(
            host="localhost",
            user="ama_poultry",
            password="Yaafrimpomaa(3)",
            database="sensor_db"
        )
        cursor = connection.cursor()

        query = """
        INSERT INTO predictions (prediction, confidence, fps, inference_time, image_path)
        VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(query, (pred, float(conf), float(fps), float(inference_time), img_path))
        connection.commit()
        connection.close()

    except Exception as e:
        log("DB ERROR", str(e))

# ================= FEATURE EXTRACTION =================
def extract_features(img_rgb):
    """
    Expects a uint8 RGB image.
    Returns HSV features (6,) and GLCM texture features (4,)
    matching the training pipeline exactly.
    """
    # RGB2HSV -- matches training extract_hsv_features()
    hsv  = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([0, 1, 1]), np.array([179, 255, 255]))

    if np.count_nonzero(mask) == 0:
        return None, None

    H, S, V = cv2.split(hsv)

    hsv_feat = [
        cv2.meanStdDev(H, mask)[0][0][0],
        cv2.meanStdDev(H, mask)[1][0][0],
        cv2.meanStdDev(S, mask)[0][0][0],
        cv2.meanStdDev(S, mask)[1][0][0],
        cv2.meanStdDev(V, mask)[0][0][0],
        cv2.meanStdDev(V, mask)[1][0][0],
    ]

    # RGB2GRAY -- matches training extract_texture_features()
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    glcm = graycomatrix(gray, distances=[1],
                        angles=[0, np.pi/4, np.pi/2, 3*np.pi/4],
                        levels=256, symmetric=True, normed=True)

    texture_feat = [
        graycoprops(glcm, 'contrast').mean(),
        graycoprops(glcm, 'homogeneity').mean(),
        graycoprops(glcm, 'energy').mean(),
        graycoprops(glcm, 'correlation').mean(),
    ]

    return hsv_feat, texture_feat

# ================= MAIN LOOP =================
frame_count    = 0
last_pred_time = 0
last_label     = None

cv2.namedWindow("AMA Poultry - Live", cv2.WINDOW_NORMAL)

while True:
    try:
        # ===== CAMERA FRAME =====
        # picam2 outputs RGB888 natively -- stays RGB throughout
        frame = picam2.capture_array()  # RGB uint8

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            continue

        start_time   = time.time()
        current_time = time.time()

        # ===== YOLO SEGMENTATION =====
        # YOLO expects BGR -- convert a copy only for YOLO
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        results   = yolo_model(frame_bgr, imgsz=IMG_SIZE, conf=CONF_THRESHOLD,
                               max_det=MAX_DET, verbose=False)
        log("YOLO", "Segmentation done")

        if results[0].masks is None or len(results[0].masks.data) == 0:
            log("YOLO", "No detection")
            preview = frame.copy()
            cv2.putText(preview, "No detection",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
            # Convert to BGR only for display
            cv2.imshow("AMA Poultry - Live", cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        mask_yolo = results[0].masks.data[0].cpu().numpy()
        mask_yolo = cv2.resize(mask_yolo, (frame.shape[1], frame.shape[0]))

        # Apply mask to RGB frame -- segmented stays RGB
        segmented = frame.copy()
        segmented[mask_yolo < 0.5] = 0

        # ===== ROI WITH PADDING =====
        x, y, w, h = cv2.boundingRect(mask_yolo.astype(np.uint8))

        padding_ratio = 0.15
        pad_w = int(w * padding_ratio)
        pad_h = int(h * padding_ratio)

        x1 = max(0, x - pad_w)
        y1 = max(0, y - pad_h)
        x2 = min(frame.shape[1], x + w + pad_w)
        y2 = min(frame.shape[0], y + h + pad_h)

        # comb is an RGB crop of the segmented frame
        comb = segmented[y1:y2, x1:x2]
        log("ROI", "Comb extracted")

        if comb.size == 0:
            continue

        # ===== PREPARE INPUT =====
        # Resize masked RGB crop -- stays RGB uint8
        comb_resized = cv2.resize(comb, (224, 224))

        # Float32 for TFLite -- NO /255 since include_preprocessing=True
        # handles internal rescaling inside MobileNetV3Small
        comb_float = comb_resized.astype(np.float32)  # RGB float32

        # ===== FEATURE EXTRACTION =====
        # comb_resized is RGB uint8 -- matches training pipeline exactly
        hsv_feat, texture_feat = extract_features(comb_resized)

        if hsv_feat is None:
            log("FEATURE", "Feature extraction failed")
            continue

        hsv_feat     = hsv_scaler.transform([hsv_feat]).astype(np.float32)
        texture_feat = texture_scaler.transform([texture_feat]).astype(np.float32)

        # ===== TFLITE INFERENCE =====
        # Input order: image, HSV, texture -- matches model input order
        # comb_float is RGB -- MobileNetV3Small expects RGB
        interpreter.set_tensor(input_details[0]['index'], np.array([comb_float]))
        interpreter.set_tensor(input_details[1]['index'], hsv_feat)
        interpreter.set_tensor(input_details[2]['index'], texture_feat)

        interpreter.invoke()

        output     = interpreter.get_tensor(output_details[0]['index'])
        log("CLASSIFIER", "Successfully classified")

        class_idx  = np.argmax(output)
        confidence = np.max(output)
        label      = label_classes[class_idx]

        if label == "pale" and confidence < 0.8:
            label = "healthy"
            log("RESULT", f"Pale confidence too low ({confidence:.2f}) -- reclassified as healthy")

        end_time       = time.time()
        inference_time = end_time - start_time
        fps            = 1 / inference_time if inference_time > 0 else 0

        log("RESULT", f"{label} ({confidence:.2f}) | FPS: {fps:.2f}")

        # ===== LIVE PREVIEW =====
        # Draw annotations on RGB frame, then convert to BGR for cv2.imshow
        preview = frame.copy()
        cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(preview, f"{label} ({confidence:.2f})",
                    (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(preview, f"FPS: {fps:.1f}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        # Convert to BGR only for display
        cv2.imshow("AMA Poultry - Live", cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # ===== DUPLICATE SUPPRESSION =====
        same_label      = (label == last_label)
        within_cooldown = (current_time - last_pred_time) < PREDICTION_COOLDOWN

        if same_label and within_cooldown:
            log("SKIP", f"Duplicate suppressed: {label}")
            continue

        last_label     = label
        last_pred_time = current_time

        # ===== SAVE IMAGE =====
        # Stack RGB arrays, annotate, then convert to BGR only at write time
        combined = np.hstack([frame, segmented])
        cv2.putText(combined, f"{label} ({confidence:.2f})",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        filename = f"{save_dir}/output_{int(time.time())}.jpg"
        # Convert to BGR only for cv2.imwrite
        cv2.imwrite(filename, cv2.cvtColor(combined, cv2.COLOR_RGB2BGR))
        log("SAVE", "Image saved")

        # ===== DATABASE =====
        send_to_db(label, confidence, fps, inference_time, filename)
        log("DATABASE", "Prediction sent to database")

        time.sleep(0.2)

    except Exception as e:
        log("ERROR", str(e))

cv2.destroyAllWindows()
picam2.stop()