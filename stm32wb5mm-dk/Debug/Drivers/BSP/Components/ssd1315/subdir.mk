################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/BSP/Components/ssd1315/ssd1315.c \
../Drivers/BSP/Components/ssd1315/ssd1315_reg.c 

OBJS += \
./Drivers/BSP/Components/ssd1315/ssd1315.o \
./Drivers/BSP/Components/ssd1315/ssd1315_reg.o 

C_DEPS += \
./Drivers/BSP/Components/ssd1315/ssd1315.d \
./Drivers/BSP/Components/ssd1315/ssd1315_reg.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/BSP/Components/ssd1315/%.o Drivers/BSP/Components/ssd1315/%.su Drivers/BSP/Components/ssd1315/%.cyclo: ../Drivers/BSP/Components/ssd1315/%.c Drivers/BSP/Components/ssd1315/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DDEBUG -DUSE_STM32WB5M_DK -c -I../Inc -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stm32wb_at" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stts22h" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/LCD" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-BSP-2f-Components-2f-ssd1315

clean-Drivers-2f-BSP-2f-Components-2f-ssd1315:
	-$(RM) ./Drivers/BSP/Components/ssd1315/ssd1315.cyclo ./Drivers/BSP/Components/ssd1315/ssd1315.d ./Drivers/BSP/Components/ssd1315/ssd1315.o ./Drivers/BSP/Components/ssd1315/ssd1315.su ./Drivers/BSP/Components/ssd1315/ssd1315_reg.cyclo ./Drivers/BSP/Components/ssd1315/ssd1315_reg.d ./Drivers/BSP/Components/ssd1315/ssd1315_reg.o ./Drivers/BSP/Components/ssd1315/ssd1315_reg.su

.PHONY: clean-Drivers-2f-BSP-2f-Components-2f-ssd1315

