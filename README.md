Create a self balancing two wheeled inverted pendulum robot remotely controlled.

The project is composed of the system level logic.
The program of the microcontroller of the robots.
An application permitting to fine tune the various parameters, preferably over the air.


Selection of the mother board
Available device: 
- Raspberry pico 2

- MB1641C (STM32WB15CC)
  The NUCLEO-WB55RG and NUCLEO-WB15CC STM32WB Nucleo-64 boards are Bluetooth® Low Energy (BLE) wireless and ultra-low-power devices embedding a 
  powerful and ultra-low-power radio compliant with the Bluetooth® Low Energy (BLE) SIG specification v5.2.
  https://www.st.com/en/evaluation-tools/nucleo-wb15cc.html

- Arduino uno R3

- MB1292B
  The STM32WB5MM-DK Discovery kit is designed as a complete demonstration and development platform for the STMicroelectronics STM32W5MMG module
  https://www.st.com/en/evaluation-tools/stm32wb5mm-dk.html
  
- MB1184C

  The 32L476GDISCOVERY helps users to develop and share applications with the STM32L4 ultra-low-power microcontrollers.The Discovery kit combines STM32L476 features 
  with LCD, LEDs, audio DAC, sensors (microphone, 3 axis gyroscope, 6 axis compass), joystick, USB OTG, Quad-SPI Flash memory, expansion and probing connectivity. 
  It includes an embedded Ammeter which measures the MCU consumption in low power modes. An external board can be connected thanks to extension and probing connectors.
  https://www.st.com/en/evaluation-tools/32l476gdiscovery.html
  
- Raspberry PI 3 Model B V1.2
  
Motor control

- Arduino Motor shield
  The Arduino Motor Shield is based on the L298 (datasheet), which is a dual full-bridge driver designed to drive inductive loads such as relays, 
  solenoids, DC and stepping motors. It lets you drive two DC motors with your Arduino board, controlling the speed and direction of each one independently. 
  You can also measure the motor current absorption of each motor, among other features. The shield is TinkerKit compatible, which means you can quickly create projects by plugging TinkerKit modules to the board.
  https://store.arduino.cc/products/arduino-motor-shield-rev3

Motor and encoders
- 29:1 Metal Gearmotor 37Dx52L mm with 64 CPR Encoder

Accelerometer

- MPU6050

Organization of the directories

## "parts"
Contains the specifications of all the parts of the project

## mb1292b-controller
Contrains the project running on the MB1292B STM32WB5M development kit.
It is based on STM32CubeIDE.

To build the MB1292B project, you must be located under the directory:
/d/Projects/gen_ai_robot_pendulum/mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32CubeIDE/Debug
and run the command "make -j16 all"
To clean the project: "make -j16 clean"

## Control implementation

The selected control architecture for the self-balancing robot is a cascade PID:

- outer loop: wheel velocity to target pitch angle
- inner loop: pitch angle to normalized motor command
- optional yaw loop: differential left/right correction

Local control modules are stored under:

- `mb1292b-controller/Utilities/Control`

The following external implementations were evaluated as references and tracked under:

- `mb1292b-controller/Utilities/ExternalControlRefs`

The project already contains `CMSIS` locally under `mb1292b-controller/Drivers/CMSIS`, which is one of the most mainstream embedded foundations for control code on Cortex-M.

## ST-Link PC interface

The dedicated wired debug / tuning / bring-up interface specification for the future PC GUI is documented in:

- `4-stlink-vcp-interface.md`

## Git Bash helpers

What to use them for:

- `cproj`: go back to the project root
- `cparts`: open the hardware notes in `parts/`
- `cmcu`: jump to the firmware project root
- `mbuild`: compile the STM32 firmware
- `mclean`: remove build artifacts
- `mrebuild`: clean and rebuild in one step

To modify the project properties , you must modify the files in STM32CubeIDE format:
- mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32CubeIDE/.project
- mb1292b-controller/Projects/STM32WB5MM-DK/Applications/BLE/BLE_Sensor/STM32CubeIDE/.cproject

## Console debug

To interract with the device, use this command:
python -m serial.tools.miniterm COM4 115200

## To run the app:

cd app-pc-monitor
py -3.11 main.py

