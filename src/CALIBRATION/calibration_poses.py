def make_grid_calibration_poses():
    poses = []
    j1_values = [-0.55, 0.0, 0.55]
    j2_values = [-1.05, -0.85, -0.65]
    j3_values = [0.85, 1.05, 1.25]
    j4 = -0.35
    gripper = 0.0

    index = 1

    for j1 in j1_values:
        for j2 in j2_values:
            for j3 in j3_values:
                poses.append(
                    {
                        "name": (
                            f"grid_{index:02d}_"
                            f"j1_{j1:+.2f}_j2_{j2:+.2f}_j3_{j3:+.2f}"
                        ),
                        "joints": (j1, j2, j3, j4, gripper),
                    }
                )
                index += 1

    return poses


DEFAULT_CALIBRATION_POSES = make_grid_calibration_poses()
