This file contains the description of the tasks in the application. Each task is responsible for a specific functionality and runs independently.

# Display Task (task_display.c)
The Display Task is responsible for updating the user interface. It runs at a fixed interval and checks for any changes in the data that needs to be displayed. If there are changes, it updates the display accordingly.
This task manages several screen to effectively present information to the user. It ensures that the display is updated in a timely manner and provides a smooth user experience. The Display Task also handles user interactions with the display, such as button presses or touch inputs, and responds accordingly.

User button B1 is used as the main action for a given screen.
User button B2 is used to switch between screens. The Display Task listens for button presses and updates the screen accordingly. It also manages the state of the buttons to ensure that they are responsive and provide feedback to the user.

## Screen Encoder display
The Screen Encoder display is responsible for showing the current value of the encoder. It updates the display whenever there is a change in the encoder value. This screen provides real-time feedback to the user about the position of the encoder. It is converted in centimeters to provide a more intuitive understanding of the encoder's position. The Display Task ensures that the encoder value is accurately displayed and updates it in a timely manner.
Encoders
  Right: 1.23 cm
  Left: 2.47 cm


# Sensor Task (task_sensor.c)
The Sensor Task is responsible for reading data from the sensors. It runs at a fixed interval and collects data from the connected sensors. The collected data is then processed and stored for later use by other tasks.

# Communication Task (task_comms.c)
The Communication Task is responsible for handling communication with external devices. It listens for incoming messages and processes them accordingly. It also sends data to external devices when necessary.

# Control Task (task_control.c)
The Control Task is responsible for the control of the motor and other actuators. It receives commands from the Communication Task and executes them to control the hardware components of the system.





