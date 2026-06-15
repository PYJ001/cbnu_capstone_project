cmake_minimum_required(VERSION 3.8)
project(joint_control)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
set(Python3_EXECUTABLE "/usr/bin/python3" CACHE FILEPATH "Python interpreter for ROS Jazzy")
find_package(Python3 3.12 EXACT REQUIRED COMPONENTS Interpreter)
set(PYTHON_INSTALL_DIR
  "lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages"
  CACHE STRING "Python package install directory"
  FORCE
)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GetPose.srv"
  "srv/MoveJoint.srv"
)

install(DIRECTORY joint_control
  DESTINATION lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages
)

install(PROGRAMS
  joint_control/joint_control_service.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME joint_control_service
)

install(PROGRAMS
  joint_control/joint_control_client.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME move_joint
)

install(PROGRAMS
  joint_control/joint_control_client.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME get_pose
)

install(PROGRAMS
  joint_control/motor_free.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME motor_free
)

install(PROGRAMS
  joint_control/joint_control_xyz_teleop.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME open_manipulator_x_teleop_xyz
)

ament_package()
