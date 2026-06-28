################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Middlewares/Third_Party/FreeRTOS/Source/croutine.c \
../Middlewares/Third_Party/FreeRTOS/Source/event_groups.c \
../Middlewares/Third_Party/FreeRTOS/Source/list.c \
../Middlewares/Third_Party/FreeRTOS/Source/queue.c \
../Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.c \
../Middlewares/Third_Party/FreeRTOS/Source/tasks.c \
../Middlewares/Third_Party/FreeRTOS/Source/timers.c 

OBJS += \
./Middlewares/Third_Party/FreeRTOS/Source/croutine.o \
./Middlewares/Third_Party/FreeRTOS/Source/event_groups.o \
./Middlewares/Third_Party/FreeRTOS/Source/list.o \
./Middlewares/Third_Party/FreeRTOS/Source/queue.o \
./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.o \
./Middlewares/Third_Party/FreeRTOS/Source/tasks.o \
./Middlewares/Third_Party/FreeRTOS/Source/timers.o 

C_DEPS += \
./Middlewares/Third_Party/FreeRTOS/Source/croutine.d \
./Middlewares/Third_Party/FreeRTOS/Source/event_groups.d \
./Middlewares/Third_Party/FreeRTOS/Source/list.d \
./Middlewares/Third_Party/FreeRTOS/Source/queue.d \
./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.d \
./Middlewares/Third_Party/FreeRTOS/Source/tasks.d \
./Middlewares/Third_Party/FreeRTOS/Source/timers.d 


# Each subdirectory must supply rules for building sources it contributes
Middlewares/Third_Party/FreeRTOS/Source/%.o Middlewares/Third_Party/FreeRTOS/Source/%.su Middlewares/Third_Party/FreeRTOS/Source/%.cyclo: ../Middlewares/Third_Party/FreeRTOS/Source/%.c Middlewares/Third_Party/FreeRTOS/Source/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DUSE_STM32WB5M_DK -DDEBUG -c -I../Core/Inc -I../App/Inc -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Control" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/MotorControl" -I../STM32_WPAN/App -I../STM32_WPAN/Target -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/AngleEstimator" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/LCD" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Utilities/lpm/tiny_lpm" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/include" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/auto" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/core/template" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Inc" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/ble/svc/Src" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/tl" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/interface/patterns/ble_thread/shci" -I"D:/Projects/gen_ai_robot_pendulum/emb-sw-ble/Middlewares/STM32_WPAN/utilities" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Middlewares-2f-Third_Party-2f-FreeRTOS-2f-Source

clean-Middlewares-2f-Third_Party-2f-FreeRTOS-2f-Source:
	-$(RM) ./Middlewares/Third_Party/FreeRTOS/Source/croutine.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/croutine.d ./Middlewares/Third_Party/FreeRTOS/Source/croutine.o ./Middlewares/Third_Party/FreeRTOS/Source/croutine.su ./Middlewares/Third_Party/FreeRTOS/Source/event_groups.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/event_groups.d ./Middlewares/Third_Party/FreeRTOS/Source/event_groups.o ./Middlewares/Third_Party/FreeRTOS/Source/event_groups.su ./Middlewares/Third_Party/FreeRTOS/Source/list.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/list.d ./Middlewares/Third_Party/FreeRTOS/Source/list.o ./Middlewares/Third_Party/FreeRTOS/Source/list.su ./Middlewares/Third_Party/FreeRTOS/Source/queue.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/queue.d ./Middlewares/Third_Party/FreeRTOS/Source/queue.o ./Middlewares/Third_Party/FreeRTOS/Source/queue.su ./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.d ./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.o ./Middlewares/Third_Party/FreeRTOS/Source/stream_buffer.su ./Middlewares/Third_Party/FreeRTOS/Source/tasks.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/tasks.d ./Middlewares/Third_Party/FreeRTOS/Source/tasks.o ./Middlewares/Third_Party/FreeRTOS/Source/tasks.su ./Middlewares/Third_Party/FreeRTOS/Source/timers.cyclo ./Middlewares/Third_Party/FreeRTOS/Source/timers.d ./Middlewares/Third_Party/FreeRTOS/Source/timers.o ./Middlewares/Third_Party/FreeRTOS/Source/timers.su

.PHONY: clean-Middlewares-2f-Third_Party-2f-FreeRTOS-2f-Source

