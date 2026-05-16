################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.c \
../Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.c 

OBJS += \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.o \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.o 

C_DEPS += \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.d \
./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/STM32WBxx_HAL_Driver/Src/%.o Drivers/STM32WBxx_HAL_Driver/Src/%.su Drivers/STM32WBxx_HAL_Driver/Src/%.cyclo: ../Drivers/STM32WBxx_HAL_Driver/Src/%.c Drivers/STM32WBxx_HAL_Driver/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DSTM32WB5Mxx -DUSE_HAL_DRIVER -DDEBUG -DUSE_STM32WB5M_DK -c -I../Inc -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/STM32WB5MM-DK" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/CMSIS/Device/ST/STM32WBxx/Include" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/STM32WBxx_HAL_Driver/Inc" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/Common" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ism330dhcx" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/ssd1315" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stm32wb_at" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Drivers/BSP/Components/stts22h" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/Fonts" -I"D:/Projects/gen_ai_robot_pendulum/stm32wb5mm-dk/Utilities/LCD" -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-STM32WBxx_HAL_Driver-2f-Src

clean-Drivers-2f-STM32WBxx_HAL_Driver-2f-Src:
	-$(RM) ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_adc_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_comp.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cortex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_crc_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_cryp_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_dma_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_exti.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_flash_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_gpio.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_hsem.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_i2c_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_ipcc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_irda.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_iwdg.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lcd.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_lptim.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_msp_template.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.o
	-$(RM) ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pcd_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pka.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_pwr_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_qspi.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rcc_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rng.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_rtc_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_sai_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smartcard_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_smbus_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_spi_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tim_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_tsc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_uart_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_usart_ex.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_hal_wwdg.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.cyclo
	-$(RM) ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_adc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_comp.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_crs.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_dma.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_exti.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_gpio.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_i2c.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lptim.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_lpuart.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pka.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_pwr.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rcc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rng.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_rtc.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_spi.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_tim.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usart.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_usb.su ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.cyclo ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.d ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.o ./Drivers/STM32WBxx_HAL_Driver/Src/stm32wbxx_ll_utils.su

.PHONY: clean-Drivers-2f-STM32WBxx_HAL_Driver-2f-Src

