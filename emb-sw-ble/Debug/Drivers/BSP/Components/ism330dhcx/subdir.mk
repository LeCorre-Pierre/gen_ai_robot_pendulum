################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/BSP/Components/ism330dhcx/ism330dhcx.c \
../Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.c 

OBJS += \
./Drivers/BSP/Components/ism330dhcx/ism330dhcx.o \
./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.o 

C_DEPS += \
./Drivers/BSP/Components/ism330dhcx/ism330dhcx.d \
./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/BSP/Components/ism330dhcx/%.o Drivers/BSP/Components/ism330dhcx/%.su Drivers/BSP/Components/ism330dhcx/%.cyclo: ../Drivers/BSP/Components/ism330dhcx/%.c Drivers/BSP/Components/ism330dhcx/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DUSE_STM32WB5M_DK -DDEBUG -c -I../Core/Inc -I../App/Inc -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Control" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/MotorControl" -I../STM32_WPAN/App -I../STM32_WPAN/Target -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/AngleEstimator" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/LCD" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/lpm/tiny_lpm" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/auto" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/template" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Src" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/tl" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/shci" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/utilities" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-BSP-2f-Components-2f-ism330dhcx

clean-Drivers-2f-BSP-2f-Components-2f-ism330dhcx:
	-$(RM) ./Drivers/BSP/Components/ism330dhcx/ism330dhcx.cyclo ./Drivers/BSP/Components/ism330dhcx/ism330dhcx.d ./Drivers/BSP/Components/ism330dhcx/ism330dhcx.o ./Drivers/BSP/Components/ism330dhcx/ism330dhcx.su ./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.cyclo ./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.d ./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.o ./Drivers/BSP/Components/ism330dhcx/ism330dhcx_reg.su

.PHONY: clean-Drivers-2f-BSP-2f-Components-2f-ism330dhcx

