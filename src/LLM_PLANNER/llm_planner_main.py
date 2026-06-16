import argparse
import json
import re

try:
    from src.LLM_PLANNER.llm import LLM
    from src.ROBOT.robot_actions import get_available_actions
except ImportError:
    from .llm import LLM
    from ..ROBOT.robot_actions import get_available_actions


class LLMPlanner:
    def __init__(
        self,
        llm=None,
    ):
        if llm is None:
            llm = LLM()

        self.llm = llm
        self.available_actions = get_available_actions()

    def launch(self):
        return True

    def run(self, *args, **kwargs):
        return self.inference(*args, **kwargs)

    def close(self):
        return True

    def inference(
        self,
        user_command,
        vlm_summary,
        yolo_robot,
        yolo_world,
    ):
        user_command = self._str(user_command)
        vlm_summary = self._str(vlm_summary)

        if yolo_robot is None:
            yolo_robot = []

        if yolo_world is None:
            yolo_world = []

        plan = self._make_plan(
            user_command      = user_command,
            vlm_summary       = vlm_summary,
            yolo_robot        = yolo_robot,
            yolo_world        = yolo_world,
            available_actions = self.available_actions,
        )

        intent = self._str(plan.get("intent")).lower()
        action_sequence = plan.get("action_sequence", [])

        action_sequence = self._validate_action_sequence(
            action_sequence=action_sequence,
            available_actions=self.available_actions,
            user_command=user_command,
        )

        print_out = self._make_print_out(
            user_command      = user_command,
            vlm_summary       = vlm_summary,
            yolo_robot        = yolo_robot,
            yolo_world        = yolo_world,
            available_actions = self.available_actions,
            intent            = intent,
            action_sequence   = action_sequence,
        )

        return action_sequence, print_out

    # ============================================================
    # user_command + vlm_summary + yolo_world + available_actions
    # -> intent + action_sequence
    # ============================================================

    def _make_plan(
        self,
        user_command,
        vlm_summary,
        yolo_robot,
        yolo_world,
        available_actions,
    ):
        prompt = f"""
You are a robot action planner.

You must decide the user's intent and the robot action sequence.

Available robot actions are given as a dictionary.
The keys are internal action names.
The values are natural-language meanings.

Use only the dictionary keys as action names in action_sequence.
Do not use the dictionary values as action names.

If the user asks what the robot can do, set intent to "available_actions_question".
If the user asks the robot to perform an action, set intent to "action_request".
If the user says hello, set intent to "action_request" and use the greeting action.
If the user asks an unrelated question, set intent to "other".

For intent "available_actions_question", action_sequence must be empty.
For intent "other", action_sequence must be empty.
For intent "action_request", make action_sequence using only available action keys.

Current action meanings:
- DNC: dance. It keeps the current gripper state.
- MOV: move to a detected object. Requires an object in yolo_world and keeps the current gripper state.
- MVA: move above a detected object. Requires an object in yolo_world and keeps the current gripper state.
- GRB: grab a detected object. Requires an object in yolo_world. It performs stand up, open gripper, move to object, close gripper, and lift.
- REL: release or open the gripper. It does not move to an object and does not need an object.
- CLS: close the gripper only. It does not move to an object and does not need an object.
- LFT: lift from the current pose. It keeps the current gripper state.
- THR: throw the currently held object. It closes the gripper, returns to default pose, then quickly stands up while opening the gripper.
- HRT: draw a heart.
- HND: hand over toward the camera/person using the nearest-depth calibration pose. It keeps the current gripper state and does not need an object.
- PRN: lie down or crouch down. It keeps the current gripper state.
- STD: stand up straight. It keeps the current gripper state.
- GRT: greet or wave hello. It keeps the current gripper state.
- BAS: return to default pose. It moves joints to 0,0,0,0 and keeps the current gripper state.

Planning rules:
- If the user asks to dance, use DNC.
- If the user asks to move to an object, use MOV with that detected object.
- If the user asks to move above an object, use MVA with that detected object.
- If the user asks to grab, pick up, or hold a detected object, use GRB with that detected object. Do not add MOV before GRB.
- If the user asks to grab my hand, grab a hand, hold my hand, or shake my hand, use GRB with obj "hand" if hand is detected.
- If the user asks to lift an object that is not already held, use GRB with that detected object.
- If the user says the robot is already holding something and asks to lift it, use LFT.
- If the user asks to release, put down, let go, or open the gripper, use REL with no object.
- If the user asks to close the gripper only, use CLS with no object. Do not use GRB.
- If the user asks to open and close the gripper, use REL then CLS.
- If the user asks to repeat open and close the gripper N times, repeat REL then CLS exactly N times.
- If the user asks to throw an object or throw what the robot is holding, use THR.
- If the user asks to draw a heart, use HRT.
- If the user asks to hand something to the camera/person, use HND.
- If the user asks the robot to lie down, crouch down, or 엎드리기/엎드려, use PRN.
- If the user asks the robot to stand up, straighten up, or 일어서기/일어서, use STD.
- If the user says hello or asks the robot to greet, wave hello, say hello, 인사하기/인사해/안녕 해줘, use GRT.
- If the user asks the robot to return to default pose, base pose, 기본 동작으로 돌아가기/기본 자세/기본 동작, use BAS.
If the user asks to put object A in/on/onto object B, use:
1. GRB with object A
2. MVA with object B
3. REL

If a required object is not detected in yolo_world, do not include actions that need that object.
Do not attach obj to actions that do not require an object: REL, CLS, LFT, THR, HRT, HND, PRN, STD, GRT, BAS, DNC.
Never use GRB as a substitute for close gripper only.

user_command:
{user_command}

vlm_summary:
{self._cut(vlm_summary, 800)}

yolo_robot:
{json.dumps(yolo_robot, ensure_ascii=False)}

yolo_world:
{json.dumps(yolo_world, ensure_ascii=False)}

available_actions:
{json.dumps(available_actions, ensure_ascii=False)}

Return only JSON:
{{
  "intent": "",
  "action_sequence": [
    {{"name": "", "obj": ""}}
  ]
}}
""".strip()

        data = self.llm.inference_json(
            text=prompt,
            default={
                "intent": "other",
                "action_sequence": [],
            },
            max_tokens=160,
        )

        if not isinstance(data, dict):
            return {
                "intent": "other",
                "action_sequence": [],
            }

        return data

    # ============================================================
    # print_out
    # ============================================================

    def _make_print_out(
        self,
        user_command,
        vlm_summary,
        yolo_robot,
        yolo_world,
        available_actions,
        intent,
        action_sequence,
    ):
        available_action_descriptions = list(available_actions.values())

        if intent == "available_actions_question":
            prompt = f"""
You are a robot arm.

The user is asking what actions you can perform.

The available actions are given as natural-language descriptions.
These are physical actions the robot can perform.

Answer using only available_action_descriptions.

Do not mention internal action names.
Do not mention codes such as DNC, MOV, MVA, GRB, REL, LFT, THR, HRT, HND, PRN, STD, GRT, or BAS.
Do not say you cannot perform physical actions.
Do not say you will perform an action now.

user_command:
{user_command}

available_action_descriptions:
{json.dumps(available_action_descriptions, ensure_ascii=False)}

Return only JSON:
{{"print_out": ""}}
""".strip()

            data = self.llm.inference_json(
                text=prompt,
                default={
                    "print_out": "I can dance, move to objects, move above objects, grab, release, lift, throw, draw a heart, hand objects over, lie down, stand up, greet, and return to the default pose."
                },
                max_tokens=100,
            )

            print_out = self._str(data.get("print_out"))

            if print_out == "":
                print_out = "I can dance, move to objects, move above objects, grab, release, lift, throw, draw a heart, hand objects over, lie down, stand up, greet, and return to the default pose."

            return print_out

        if len(action_sequence) == 0:
            prompt = f"""
You are a robot arm.

No executable robot action was selected.
Make a short natural response to the user.

Do not mention internal action names.
Do not mention codes such as DNC, MOV, MVA, GRB, REL, LFT, THR, HRT, HND, PRN, STD, GRT, or BAS.

user_command:
{user_command}

vlm_summary:
{self._cut(vlm_summary, 800)}

yolo_world:
{json.dumps(yolo_world, ensure_ascii=False)}

available_action_descriptions:
{json.dumps(available_action_descriptions, ensure_ascii=False)}

Return only JSON:
{{"print_out": ""}}
""".strip()

            data = self.llm.inference_json(
                text=prompt,
                default={"print_out": "Sorry, I cannot perform that action."},
                max_tokens=100,
            )

            print_out = self._str(data.get("print_out"))

            if print_out == "":
                print_out = "Sorry, I cannot perform that action."

            return print_out

        selected_action_descriptions = self._make_selected_action_descriptions(
            action_sequence=action_sequence,
            available_actions=available_actions,
        )

        prompt = f"""
You are a robot arm.

Make a short natural response to the user.

The robot will perform only selected_action_descriptions.
Do not mention internal action names.
Do not mention codes such as DNC, MOV, MVA, GRB, REL, LFT, THR, HRT, HND, PRN, STD, GRT, or BAS.
Do not invent new actions.

user_command:
{user_command}

vlm_summary:
{self._cut(vlm_summary, 800)}

yolo_robot:
{json.dumps(yolo_robot, ensure_ascii=False)}

yolo_world:
{json.dumps(yolo_world, ensure_ascii=False)}

selected_action_descriptions:
{json.dumps(selected_action_descriptions, ensure_ascii=False)}

Return only JSON:
{{"print_out": ""}}
""".strip()

        data = self.llm.inference_json(
            text=prompt,
            default={"print_out": "Okay."},
            max_tokens=100,
        )

        print_out = self._str(data.get("print_out"))

        if print_out == "":
            print_out = "Okay."

        return print_out

    def _make_selected_action_descriptions(
        self,
        action_sequence,
        available_actions,
    ):
        result = []

        for action in action_sequence:
            if not isinstance(action, dict):
                continue

            name = self._str(action.get("name")).upper()
            obj = self._normalize_object_name(action.get("obj"))

            description = available_actions.get(name, "")

            if description == "":
                continue

            item = {"action": description}

            if obj != "":
                item["object"] = obj

            result.append(item)

        return result

    # ============================================================
    # Validation
    # ============================================================

    def _validate_action_sequence(
        self,
        action_sequence,
        available_actions,
        user_command="",
    ):
        if not isinstance(action_sequence, list):
            return []

        gripper_sequence = self._make_gripper_sequence(user_command)

        if gripper_sequence is not None:
            return gripper_sequence

        allowed_names = set(available_actions.keys())
        object_action_names = {"MOV", "MVA", "GRB"}

        result = []

        for action in action_sequence:
            if not isinstance(action, dict):
                continue

            name = self._str(action.get("name")).upper()
            obj = self._normalize_object_name(action.get("obj"))

            if name not in allowed_names:
                continue

            clean_action = {"name": name}

            if name in object_action_names:
                if obj == "":
                    continue
                clean_action["obj"] = obj

            result.append(clean_action)

        return result

    def _make_gripper_sequence(self, user_command):
        text = self._str(user_command).lower()

        if "gripper" not in text:
            return None

        wants_open = "open" in text
        wants_close = "close" in text

        if wants_open and wants_close:
            repeat_count = self._extract_repeat_count(text)
            sequence = []

            for _ in range(repeat_count):
                sequence.append({"name": "REL"})
                sequence.append({"name": "CLS"})

            return sequence

        if wants_close:
            return [{"name": "CLS"}]

        if wants_open:
            return [{"name": "REL"}]

        return None

    def _extract_repeat_count(self, text):
        match = re.search(r"\b(?:repeat|x|times?)\s*(\d+)\b", text)

        if match is None:
            match = re.search(r"\b(\d+)\s*(?:times?|x)\b", text)

        if match is not None:
            return max(1, min(20, int(match.group(1))))

        word_counts = {
            "once": 1,
            "one": 1,
            "twice": 2,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }

        for word, count in word_counts.items():
            if re.search(rf"\b{word}\b", text):
                return count

        return 1

    def _normalize_object_name(self, obj):
        obj = self._str(obj).lower()
        obj = obj.replace("'s", "")
        obj = " ".join(obj.split())

        if "hand" in obj:
            return "hand"

        if "bottle" in obj:
            return "bottle"

        if "cup" in obj or "mug" in obj:
            return "cup"

        return obj

    # ============================================================
    # Helpers
    # ============================================================

    def _str(self, value):
        if value is None:
            return ""

        return str(value).strip()

    def _cut(self, text, n):
        text = self._str(text)

        if len(text) <= n:
            return text

        return text[:n]

##########################################################################################################

def main():
    planner = LLMPlanner()

    test_inputs = [
        {
            "user_command": "tell me what you can do",
            "vlm_summary": "A robot arm is on a desk.",
            "yolo_robot": [],
            "yolo_world": [],
        },
        {
            "user_command": "what actions can you perform?",
            "vlm_summary": "A robot arm is on a desk.",
            "yolo_robot": [],
            "yolo_world": [],
        },
        {
            "user_command": "hello",
            "vlm_summary": "A robot arm is on a desk.",
            "yolo_robot": [],
            "yolo_world": [],
        },
        {
            "user_command": "춤춰",
            "vlm_summary": "A robot arm is on a desk.",
            "yolo_robot": [],
            "yolo_world": [],
        },
        {
            "user_command": "병을 잡아줘",
            "vlm_summary": "A robot arm is on a desk. A bottle is visible.",
            "yolo_robot": [],
            "yolo_world": [
                {"name": "bottle", "u": 320, "v": 240, "d": 0.52},
            ],
        },
        {
            "user_command": "악수한 다음 병을 잡아서 던져줘",
            "vlm_summary": "A robot arm is on a desk. A bottle is visible.",
            "yolo_robot": [],
            "yolo_world": [
                {"name": "bottle", "u": 320, "v": 240, "d": 0.52},
            ],
        },
    ]

    for test_input in test_inputs:
        print("\n" + "=" * 60)
        print("[USER_COMMAND]")
        print(test_input["user_command"])

        action_sequence, print_out = planner.inference(
            user_command=test_input["user_command"],
            vlm_summary=test_input["vlm_summary"],
            yolo_robot=test_input["yolo_robot"],
            yolo_world=test_input["yolo_world"],
        )

        print("[ACTION_SEQUENCE]")
        print(action_sequence)

        print("[PRINT_OUT]")
        print(print_out)

if __name__ == "__main__":
    main()
