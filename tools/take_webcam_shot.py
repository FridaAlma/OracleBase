import cv2
import os

cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("ERRORE: Impossibile aprire la webcam 1")
    exit(1)

# Lascia un attimo per l'autofocus/white balance
for _ in range(10):
    cap.read()

ret, frame = cap.read()

if ret:
    output_path = "webcam_photo.jpg"
    cv2.imwrite(output_path, frame)
    file_size = os.path.getsize(output_path)
    print(f"Foto salvata: {output_path} ({file_size} bytes)")
else:
    print("ERRORE: Impossibile catturare il frame")

cap.release()
cv2.destroyAllWindows()