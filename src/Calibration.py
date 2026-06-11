import csv
from pathlib import Path

import numpy as np


class CalibrationModel:
    def __init__(self, samples, k=4, power=2.0):
        if len(samples) == 0:
            raise ValueError("calibration samples are empty")

        self.samples = samples
        self.k = max(1, int(k))
        self.power = float(power)

        self.x = np.array([sample["uvd"] for sample in samples], dtype=np.float32)
        self.y = np.array([sample["joints"] for sample in samples], dtype=np.float32)

        self.x_mean = self.x.mean(axis=0)
        self.x_std = self.x.std(axis=0)
        self.x_std[self.x_std < 1e-6] = 1.0

    @classmethod
    def from_latest_or_path(cls, csv_path=None, search_dir="robot_camera_calibration_samples", k=4):
        path = cls._resolve_csv_path(csv_path, search_dir)

        if path is None:
            raise FileNotFoundError("calibration csv was not found")

        return cls.from_csv(path, k=k)

    @classmethod
    def from_csv(cls, csv_path, k=4):
        path = Path(csv_path)
        samples = []

        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                sample = cls._parse_row(row)

                if sample is not None:
                    samples.append(sample)

        model = cls(samples=samples, k=k)
        model.csv_path = path
        return model

    def predict(self, u, v, d):
        query = np.array(
            [
                self._float_or_mean(u, 0),
                self._float_or_mean(v, 1),
                self._float_or_mean(d, 2),
            ],
            dtype=np.float32,
        )

        x_norm = (self.x - self.x_mean) / self.x_std
        query_norm = (query - self.x_mean) / self.x_std

        distances = np.linalg.norm(x_norm - query_norm, axis=1)
        k = min(self.k, len(distances))
        nearest_idx = np.argsort(distances)[:k]
        nearest_distances = distances[nearest_idx]

        if nearest_distances[0] < 1e-6:
            return tuple(float(value) for value in self.y[nearest_idx[0]])

        weights = 1.0 / np.power(nearest_distances + 1e-6, self.power)
        weights = weights / weights.sum()

        prediction = np.sum(self.y[nearest_idx] * weights[:, None], axis=0)
        return tuple(float(value) for value in prediction)

    def _float_or_mean(self, value, index):
        parsed = self._parse_float(value)

        if parsed is None:
            return float(self.x_mean[index])

        return parsed

    @staticmethod
    def _resolve_csv_path(csv_path, search_dir):
        if csv_path is not None:
            path = Path(csv_path)

            if path.exists():
                return path

            raise FileNotFoundError(f"calibration csv does not exist: {path}")

        root = Path(search_dir)

        if not root.exists():
            return None

        paths = sorted(root.glob("*/robot_camera_calibration_samples.csv"))

        if len(paths) == 0:
            return None

        return paths[-1]

    @classmethod
    def _parse_row(cls, row):
        u = cls._parse_float(row.get("robot_u"))
        v = cls._parse_float(row.get("robot_v"))
        d = cls._parse_float(row.get("robot_d"))

        joints = [
            cls._parse_float(row.get("j1")),
            cls._parse_float(row.get("j2")),
            cls._parse_float(row.get("j3")),
            cls._parse_float(row.get("j4")),
            cls._parse_float(row.get("gripper")),
        ]

        if u is None or v is None or d is None:
            return None

        if any(value is None for value in joints):
            return None

        return {
            "uvd": [u, v, d],
            "joints": joints,
        }

    @staticmethod
    def _parse_float(value):
        if value is None:
            return None

        text = str(value).strip()

        if text == "" or text.lower() == "none":
            return None

        try:
            return float(text)
        except ValueError:
            return None
