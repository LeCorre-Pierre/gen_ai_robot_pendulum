################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.c \
../Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.c 

OBJS += \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.o \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.o 

C_DEPS += \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.d \
./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/BSP/STM32WB5MM-DK/%.o Drivers/BSP/STM32WB5MM-DK/%.su Drivers/BSP/STM32WB5MM-DK/%.cyclo: ../Drivers/BSP/STM32WB5MM-DK/%.c Drivers/BSP/STM32WB5MM-DK/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DDEBUG -DUSE_STM32WB5M_DK -c -I../Inc -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stm32wb_at" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stts22h" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/LCD" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-BSP-2f-STM32WB5MM-2d-DK

clean-Drivers-2f-BSP-2f-STM32WB5MM-2d-DK:
	-$(RM) ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_bus.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_env_sensors_ex.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_lcd.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors.su ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.cyclo ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.d ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.o ./Drivers/BSP/STM32WB5MM-DK/stm32wb5mm_dk_motion_sensors_ex.su

.PHONY: clean-Drivers-2f-BSP-2f-STM32WB5MM-2d-DK

