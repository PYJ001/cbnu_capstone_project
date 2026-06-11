import io
import time

import cv2
import ollama
from PIL import Image


class VLM:
    def __init__(
        self,
        model_name="qwen2.5vl:3b",
        max_size=384,
        jpeg_quality=70,
    ):
        self.model_name = model_name
        self.max_size = max_size
        self.jpeg_quality = jpeg_quality

        #print(f"[VLM] model: {model_name}")
        #print(f"[VLM] max_size: {max_size}")
        #print(f"[VLM] jpeg_quality: {jpeg_quality}")

    def inference(self, IN):
        """
        IN:
        - OpenCV BGR frame
        """

        if IN is None:
            return "No image is available."

        image_bytes = self._frame_to_jpeg_bytes(IN)

        prompt = """
Describe the image briefly.

Return only this format:

scene: one short sentence describing the scene
objects: visible object names separated by commas

Rules:
- Mention only objects that are clearly visible.
- Use generic object category names, not brand names or detailed descriptions.
- Include visible hands if they are present.
- Do not include people, humans, faces, men, or women in objects.
- Prefer small manipulable tabletop objects and hands.
- If you see a coffee bottle, plastic bottle, or drink bottle, write bottle.
- If you see a human hand, write hand.
- Return at most 8 object names.
- Do not infer hidden or uncertain objects.
- Do not add safety, reachability, robot context, or extra explanation.
- Keep it short.
"""

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_bytes],
                    }
                ],
                options={
                    "temperature": 0,
                    "num_predict": 80,
                },
            )

            depiction = response["message"]["content"].strip()
            #print(f"[VLM] depiction: {depiction}")
            return depiction

        except Exception as e:
            print(f"[VLM] inference failed: {e}")
            return "VLM failed to describe the image."

    def infer_scene_and_objects(self, frame):
        summary = self.inference(frame)
        objects = self.extract_object_classes(summary)

        return {
            "summary": summary,
            "objects": objects,
        }

    @staticmethod
    def extract_object_classes(summary):
        if summary is None:
            return []

        text = str(summary)
        object_text = ""

        for line in text.splitlines():
            key, sep, value = line.partition(":")

            if sep == "" or key.strip().lower() != "objects":
                continue

            object_text = value
            break

        if object_text == "":
            return []

        objects = []
        seen = set()

        for item in object_text.split(","):
            name = VLM.normalize_object_class(item)

            if name in ["", "none", "nothing", "no objects", "n/a"]:
                continue

            if VLM.is_ignored_world_class(name):
                continue

            if name in seen:
                continue

            seen.add(name)
            objects.append(name)

            if len(objects) >= 8:
                break

        return objects

    @staticmethod
    def normalize_object_class(name):
        name = str(name).strip().lower()
        name = name.replace(".", "")

        aliases = [
            ("hand", ["hand", "human hand", "person hand", "person's hand"]),
            ("bottle", ["bottle", "coffee bottle", "drink bottle", "plastic bottle"]),
            ("cup", ["cup", "mug", "coffee cup", "paper cup"]),
            ("box", ["box", "cardboard box"]),
            ("basket", ["basket", "bin", "container"]),
            ("apple", ["apple"]),
            ("banana", ["banana"]),
        ]

        for canonical, keywords in aliases:
            for keyword in keywords:
                if keyword in name:
                    return canonical

        words_to_remove = [
            "a ",
            "an ",
            "the ",
            "small ",
            "large ",
            "plastic ",
            "paper ",
            "metal ",
            "wooden ",
            "coffee ",
            "maxwell house ",
        ]

        for word in words_to_remove:
            name = name.replace(word, "")

        return " ".join(name.split())

    @staticmethod
    def is_ignored_world_class(name):
        ignored = {
            "person",
            "human",
            "man",
            "woman",
            "face",
            "robot",
            "robot arm",
            "end effector",
            "camera",
            "desk",
            "table",
            "chair",
            "office chair",
            "cubicle",
            "wall",
            "floor",
            "monitor",
            "computer",
            "computer monitor",
            "screen",
            "laptop",
            "keyboard",
            "mouse",
            "lamp",
            "phone",
            "headphones",
            "remote",
            "power strip",
            "wall socket",
            "socket",
            "cable",
            "wire",
        }

        return name in ignored

    def _frame_to_jpeg_bytes(self, frame):
        h, w = frame.shape[:2]

        scale = self.max_size / max(h, w)

        if scale < 1.0:
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)

        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=self.jpeg_quality,
            optimize=True,
        )
        return buffer.getvalue()

def main():
    """
    VLM webcam test

    키:
    - SPACE : 현재 웹캠 프레임으로 VLM 추론
    - ESC   : 종료
    """

    camera_index = 4
    model_name = "qwen2.5vl:7b"

    vlm = VLM(model_name=model_name)

    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"[ERROR] failed to open webcam: camera_index={camera_index}")
        return

    print(f"[CAMERA] opened webcam: camera_index={camera_index}")
    print("[KEY]")
    print("  SPACE : run VLM inference")
    print("  ESC   : quit")

    last_result = "Press SPACE to run VLM inference."

    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("[ERROR] failed to read frame from webcam")
            break

        display = frame.copy()

        cv2.putText(
            display,
            last_result[:80],
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow("VLM Webcam Test", display)

        key = cv2.waitKey(1) & 0xFF

        if key == 27:
            print("[MAIN] ESC pressed. Exit.")
            break

        elif key == ord(" "):
            print()
            print("=" * 60)
            print("[MAIN] VLM inference start")
            print("=" * 60)

            start_time = time.time()

            input_frame = frame.copy()
            last_result = vlm.inference(input_frame)

            elapsed = time.time() - start_time

            print("=" * 60)
            print("[MAIN] VLM inference done")
            print(f"[MAIN] elapsed: {elapsed:.2f} sec")
            print(f"[MAIN] result : {last_result}")
            print("=" * 60)
            print()

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
