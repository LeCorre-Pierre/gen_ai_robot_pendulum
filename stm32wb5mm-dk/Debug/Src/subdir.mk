################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Src/main.c \
../Src/stm32wbxx_hal_msp.c \
../Src/stm32wbxx_it.c \
../Src/system_stm32wbxx.c 

OBJS += \
./Src/main.o \
./Src/stm32wbxx_hal_msp.o \
./Src/stm32wbxx_it.o \
./Src/system_stm32wbxx.o 

C_DEPS += \
./Src/main.d \
./Src/stm32wbxx_hal_msp.d \
./Src/stm32wbxx_it.d \
./Src/system_stm32wbxx.d 


# Each subdirectory must supply rules for building sources it contributes
Src/%.o Src/%.su Src/%.cyclo: ../Src/%.c Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DDEBUG -DUSE_STM32WB5M_DK -c -I../Inc -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/STM32WBxx_HAL_Driver/Inc" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Src

clean-Src:
	-$(RM) ./Src/main.cyclo ./Src/main.d ./Src/main.o ./Src/main.su ./Src/stm32wbxx_hal_msp.cyclo ./Src/stm32wbxx_hal_msp.d ./Src/stm32wbxx_hal_msp.o ./Src/stm32wbxx_hal_msp.su ./Src/stm32wbxx_it.cyclo ./Src/stm32wbxx_it.d ./Src/stm32wbxx_it.o ./Src/stm32wbxx_it.su ./Src/system_stm32wbxx.cyclo ./Src/system_stm32wbxx.d ./Src/system_stm32wbxx.o ./Src/system_stm32wbxx.su

.PHONY: clean-Src

