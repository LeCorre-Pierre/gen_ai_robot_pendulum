################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Middlewares/STM32_WPAN/ble/core/auto/ble_events.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.c \
../Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.c 

OBJS += \
./Middlewares/STM32_WPAN/ble/core/auto/ble_events.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.o \
./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.o 

C_DEPS += \
./Middlewares/STM32_WPAN/ble/core/auto/ble_events.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.d \
./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.d 


# Each subdirectory must supply rules for building sources it contributes
Middlewares/STM32_WPAN/ble/core/auto/%.o Middlewares/STM32_WPAN/ble/core/auto/%.su Middlewares/STM32_WPAN/ble/core/auto/%.cyclo: ../Middlewares/STM32_WPAN/ble/core/auto/%.c Middlewares/STM32_WPAN/ble/core/auto/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DUSE_STM32WB5M_DK -DDEBUG -c -I../Core/Inc -I../STM32_WPAN/App -I../STM32_WPAN/Target -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/lpm/tiny_lpm" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/auto" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/template" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/tl" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/shci" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/utilities" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-core-2f-auto

clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-core-2f-auto:
	-$(RM) ./Middlewares/STM32_WPAN/ble/core/auto/ble_events.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_events.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_events.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_events.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_gap_aci.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_gatt_aci.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_gen_aci.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_hal_aci.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_hci_le.su ./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.cyclo ./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.d ./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.o ./Middlewares/STM32_WPAN/ble/core/auto/ble_l2cap_aci.su

.PHONY: clean-Middlewares-2f-STM32_WPAN-2f-ble-2f-core-2f-auto

