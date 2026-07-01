################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../App/Src/imu.c \
../App/Src/task_comms.c \
../App/Src/task_control.c \
../App/Src/task_display.c \
../App/Src/task_sensors.c \
../App/Src/vcp_protocol.c 

OBJS += \
./App/Src/imu.o \
./App/Src/task_comms.o \
./App/Src/task_control.o \
./App/Src/task_display.o \
./App/Src/task_sensors.o \
./App/Src/vcp_protocol.o 

C_DEPS += \
./App/Src/imu.d \
./App/Src/task_comms.d \
./App/Src/task_control.d \
./App/Src/task_display.d \
./App/Src/task_sensors.d \
./App/Src/vcp_protocol.d 


# Each subdirectory must supply rules for building sources it contributes
App/Src/%.o App/Src/%.su App/Src/%.cyclo: ../App/Src/%.c App/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DUSE_STM32WB5M_DK -DDEBUG -c -I../Core/Inc -I../App/Inc -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Control" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/MotorControl" -I../STM32_WPAN/App -I../STM32_WPAN/Target -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/AngleEstimator" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/LCD" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/lpm/tiny_lpm" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/auto" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/template" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Src" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/tl" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/shci" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/utilities" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-App-2f-Src

clean-App-2f-Src:
	-$(RM) ./App/Src/imu.cyclo ./App/Src/imu.d ./App/Src/imu.o ./App/Src/imu.su ./App/Src/task_comms.cyclo ./App/Src/task_comms.d ./App/Src/task_comms.o ./App/Src/task_comms.su ./App/Src/task_control.cyclo ./App/Src/task_control.d ./App/Src/task_control.o ./App/Src/task_control.su ./App/Src/task_display.cyclo ./App/Src/task_display.d ./App/Src/task_display.o ./App/Src/task_display.su ./App/Src/task_sensors.cyclo ./App/Src/task_sensors.d ./App/Src/task_sensors.o ./App/Src/task_sensors.su ./App/Src/vcp_protocol.cyclo ./App/Src/vcp_protocol.d ./App/Src/vcp_protocol.o ./App/Src/vcp_protocol.su

.PHONY: clean-App-2f-Src

