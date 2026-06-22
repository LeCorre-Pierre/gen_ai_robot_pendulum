################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.c 

OBJS += \
./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.o 

C_DEPS += \
./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.d 


# Each subdirectory must supply rules for building sources it contributes
Middlewares/STM32_WPAN/ble/svc/Src/%.o Middlewares/STM32_WPAN/ble/svc/Src/%.su Middlewares/STM32_WPAN/ble/svc/Src/%.cyclo: ../Middlewares/STM32_WPAN/ble/svc/Src/%.c Middlewares/STM32_WPAN/ble/svc/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DUSE_STM32WB5M_DK -DDEBUG -c -I../Core/Inc -I../STM32_WPAN/App -I../STM32_WPAN/Target -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/lpm/tiny_lpm" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/auto" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/template" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/tl" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/shci" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/utilities" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-svc-2f-Src

clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-svc-2f-Src:
	-$(RM) ./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.cyclo ./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.d ./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.o ./Middlewares/STM32_WPAN/ble/svc/Src/svc_ctl.su

.PHONY: clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-svc-2f-Src

