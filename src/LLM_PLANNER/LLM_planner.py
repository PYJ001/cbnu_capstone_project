import json

from .LLM import LLM
from src.ROBOT.robot_actions import get_available_actions

class LLMPlanner:
    def __init__(
        self,
        llm=None,
    ):
        if llm is None:
            llm = LLM()

        self.llm = llm
        self.available_actions = get_available_actions()

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
            yolo_world=yolo_world,
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
If the user only says hello or asks an unrelated question, set intent to "other".

For intent "available_actions_question", action_sequence must be empty.
For intent "other", action_sequence must be empty.
For intent "action_request", make action_sequence using only available action keys.

If the user asks to grab an object, use GRB with that detected object.
GRB already includes move-to-object, pre-grasp, close gripper, and lift.
Do not add MOV before GRB.

If the user asks to lift an object, use GRB with that detected object.
If the robot is already holding something and the user asks to lift it, use LFT.

If the user asks to release, put down, or let go of an object, use REL.
If the user asks to throw an object, use THR.
If the user asks to draw a heart, use HRT.
If the user asks to hand an object to the camera/person, use HND.
If the user asks to move above an object, use MVA with that object.
If the user asks to put object A in/on/onto object B, use:
1. GRB with object A
2. MVA with object B
3. REL

If a required object is not detected in yolo_world, do not include actions that need that object.

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
Do not mention codes such as DNC, WAV, SKH, MOV, MVA, GRB, REL, TRW, LFT, THR, HRT, or HND.
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
                    "print_out": "I can dance, wave, move to objects, grab, release, lift, throw, draw a heart, and hand objects over."
                },
                max_tokens=100,
            )

            print_out = self._str(data.get("print_out"))

            if print_out == "":
                print_out = "I can dance, wave, move to objects, grab, release, lift, throw, draw a heart, and hand objects over."

            return print_out

        if len(action_sequence) == 0:
            prompt = f"""
You are a robot arm.

No executable robot action was selected.
Make a short natural response to the user.

Do not mention internal action names.
Do not mention codes such as DNC, WAV, SKH, MOV, MVA, GRB, REL, TRW, LFT, THR, HRT, or HND.

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
Do not mention codes such as DNC, WAV, SKH, MOV, MVA, GRB, REL, TRW, LFT, THR, HRT, or HND.
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
            obj = self._str(action.get("obj")).lower()

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
        yolo_world=None,
    ):
        if not isinstance(action_sequence, list):
            return []

        allowed_names = set(available_actions.keys())
        object_required_names = {"MOV", "MVA", "GRB"}
        detected_names = self._detected_object_names(yolo_world)

        result = []

        for action in action_sequence:
            if not isinstance(action, dict):
                continue

            name = self._str(action.get("name")).upper()
            obj = self._str(action.get("obj")).lower()

            if name not in allowed_names:
                continue

            if name in object_required_names:
                if obj == "":
                    continue

                if obj not in detected_names:
                    continue

            clean_action = {"name": name}

            if obj != "":
                clean_action["obj"] = obj

            result.append(clean_action)

        return result

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

    def _detected_object_names(self, yolo_world):
        if isinstance(yolo_world, dict):
            yolo_world = [yolo_world]

        if not isinstance(yolo_world, list):
            return set()

        names = set()

        for item in yolo_world:
            if not isinstance(item, dict):
                continue

            name = self._str(item.get("name")).lower()

            if name != "":
                names.add(name)

        return names

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
