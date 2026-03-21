################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

-include ../makefile.init

RM := rm -rf

# All of the sources participating in the build are defined here
-include sources.mk
-include Utilities/subdir.mk
-include Middlewares/STM32_WPAN/subdir.mk
-include Drivers/STM32WBxx_HAL_Driver/subdir.mk
-include Drivers/CMSIS/subdir.mk
-include Drivers/BSP/STM32WB5MM-DK/subdir.mk
-include Drivers/BSP/Components/subdir.mk
-include Application/User/STM32_WPAN/Target/subdir.mk
-include Application/User/STM32_WPAN/App/subdir.mk
-include Application/User/Core/vl53l0x/subdir.mk
-include Application/User/Core/subdir.mk
-include Application/Startup/subdir.mk
-include objects.mk

ifneq ($(MAKECMDGOALS),clean)
ifneq ($(strip $(S_DEPS)),)
-include $(S_DEPS)
endif
ifneq ($(strip $(S_UPPER_DEPS)),)
-include $(S_UPPER_DEPS)
endif
ifneq ($(strip $(C_DEPS)),)
-include $(C_DEPS)
endif
endif

-include ../makefile.defs

OPTIONAL_TOOL_DEPS := \
$(wildcard ../makefile.defs) \
$(wildcard ../makefile.init) \
$(wildcard ../makefile.targets) \


BUILD_ARTIFACT_NAME := BLE_Sensor
BUILD_ARTIFACT_EXTENSION := elf
BUILD_ARTIFACT_PREFIX :=
BUILD_ARTIFACT := $(BUILD_ARTIFACT_PREFIX)$(BUILD_ARTIFACT_NAME)$(if $(BUILD_ARTIFACT_EXTENSION),.$(BUILD_ARTIFACT_EXTENSION),)

# Add inputs and outputs from these tool invocations to the build variables 
EXECUTABLES += \
BLE_Sensor.elf \

MAP_FILES += \
BLE_Sensor.map \

SIZE_OUTPUT += \
default.size.stdout \

OBJDUMP_LIST += \
BLE_Sensor.list \

OBJCOPY_HEX += \
BLE_Sensor.hex \


# All Target
all: main-build

# Main-build Target
main-build: BLE_Sensor.elf secondary-outputs

# Tool invocations
BLE_Sensor.elf BLE_Sensor.map: $(OBJS) $(USER_OBJS) D:\Projects\gen_ai_robot_pendulum\mb1292b-controller\Projects\STM32WB5MM-DK\Applications\BLE\BLE_Sensor\STM32CubeIDE\STM32WB5MMGHX_FLASH.ld makefile objects.list $(OPTIONAL_TOOL_DEPS)
	arm-none-eabi-gcc -o "BLE_Sensor.elf" @"objects.list" $(USER_OBJS) $(LIBS) -mcpu=cortex-m4 -T"D:\Projects\gen_ai_robot_pendulum\mb1292b-controller\Projects\STM32WB5MM-DK\Applications\BLE\BLE_Sensor\STM32CubeIDE\STM32WB5MMGHX_FLASH.ld" --specs=nosys.specs -Wl,-Map="BLE_Sensor.map" -Wl,--gc-sections -static --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -u _printf_float -Wl,--start-group -lc -lm -Wl,--end-group
	@echo 'Finished building target: $@'
	@echo ' '

default.size.stdout: $(EXECUTABLES) makefile objects.list $(OPTIONAL_TOOL_DEPS)
	arm-none-eabi-size  $(EXECUTABLES)
	@echo 'Finished building: $@'
	@echo ' '

BLE_Sensor.list: $(EXECUTABLES) makefile objects.list $(OPTIONAL_TOOL_DEPS)
	arm-none-eabi-objdump -h -S $(EXECUTABLES) > "BLE_Sensor.list"
	@echo 'Finished building: $@'
	@echo ' '

BLE_Sensor.hex: $(EXECUTABLES) makefile objects.list $(OPTIONAL_TOOL_DEPS)
	arm-none-eabi-objcopy  -O ihex $(EXECUTABLES) "BLE_Sensor.hex"
	@echo 'Finished building: $@'
	@echo ' '

# Other Targets
clean:
	-$(RM) BLE_Sensor.elf BLE_Sensor.hex BLE_Sensor.list BLE_Sensor.map default.size.stdout
	-@echo ' '

secondary-outputs: $(SIZE_OUTPUT) $(OBJDUMP_LIST) $(OBJCOPY_HEX)

fail-specified-linker-script-missing:
	@echo 'Error: Cannot find the specified linker script. Check the linker settings in the build configuration.'
	@exit 2

warn-no-linker-script-specified:
	@echo 'Warning: No linker script specified. Check the linker settings in the build configuration.'

.PHONY: all clean dependents main-build fail-specified-linker-script-missing warn-no-linker-script-specified

-include ../makefile.targets
