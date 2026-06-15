import io

import cv2
from PIL import Image


class VLM:
    def __init__(
        self,
        enabled=True,
        model_name="qwen2.5vl:3b",
        max_size=384,
        jpeg_quality=70,
    ):
        self.enabled = bool(enabled)
        self.model_name = model_name
        self.max_size = max_size
        self.jpeg_quality = jpeg_quality
        self.latest_summary = ""
        self.latest_objects = []

    def inference(self, frame, user_command=""):
        if not self.enabled:
            return self._latest_result()

        result = self.infer_scene_and_objects(
            frame=frame,
            user_command=user_command,
        )
        self.latest_summary = result.get("summary", "")
        self.latest_objects = result.get("objects", [])
        return self._latest_result()

    def infer_scene_and_objects(self, frame, user_command=""):
        summary = self._describe_frame(
            frame=frame,
            user_command=user_command,
        )
        objects = self.extract_object_classes(summary)

        return {
            "summary": summary,
            "objects": objects,
        }

    def _describe_frame(self, frame, user_command=""):
        if frame is None:
            return "No image is available."

        try:
            import ollama
        except Exception as exc:
            print(f"[VLM] disabled: {exc}")
            self.enabled = False
            return "VLM is not available."

        image_bytes = self._frame_to_jpeg_bytes(frame)
        prompt = f"""
Describe the image briefly.

User command:
{user_command}

Return only this format:

scene: one short sentence describing the scene
objects: visible object names separated by commas

Rules:
- Mention only objects that are clearly visible.
- Prefer objects that are relevant to the user command.
- Use generic object category names, not brand names or detailed descriptions.
- Include visible hands if they are present.
- Do not include people, humans, faces, men, or women in objects.
- Prefer small manipulable tabletop objects and hands.
- If you see a coffee bottle, plastic bottle, or drink bottle, write bottle.
- If you see a human hand, write hand.
- Return at most 15 object names.
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
            return response["message"]["content"].strip()
        except Exception as exc:
            print(f"[VLM] inference failed: {exc}")
            return "VLM failed to describe the image."

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

    def _latest_result(self):
        return {
            "summary": self.latest_summary,
            "objects": self.latest_objects.copy(),
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

            if len(objects) >= 15:
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
