
#include "stm32wbxx.h"

#if !defined  (HSE_VALUE)
  #define HSE_VALUE    (32000000UL) /*!< Value of the External oscillator in Hz */
#endif /* HSE_VALUE */

#if !defined  (MSI_VALUE)
   #define MSI_VALUE    (4000000UL) /*!< Value of the Internal oscillator in Hz*/
#endif /* MSI_VALUE */

#if !defined  (HSI_VALUE)
  #define HSI_VALUE    (16000000UL) /*!< Value of the Internal oscillator in Hz*/
#endif /* HSI_VALUE */

#if !defined  (LSI_VALUE) 
 #define LSI_VALUE  (32000UL)       /*!< Value of LSI in Hz*/
#endif /* LSI_VALUE */ 

#if !defined  (LSE_VALUE)
  #define LSE_VALUE    (32768UL)    /*!< Value of LSE in Hz*/
#endif /* LSE_VALUE */

#if defined(USER_VECT_TAB_ADDRESS)
 /*!< Uncomment this line for user vector table remap in Sram else user remap
      will be done in Flash. */
/* #define VECT_TAB_SRAM */
#if defined(VECT_TAB_SRAM)
#define VECT_TAB_BASE_ADDRESS   SRAM1_BASE      /*!< Vector Table base address field.
                                                     This value must be a multiple of 0x200. */
#define VECT_TAB_OFFSET         0x00000000U     /*!< Vector Table base offset field.
                                                     This value must be a multiple of 0x200. */
#else
#define VECT_TAB_BASE_ADDRESS   FLASH_BASE      /*!< Vector Table base address field.
                                                     This value must be a multiple of 0x200. */
#define VECT_TAB_OFFSET         0x00000000U     /*!< Vector Table base offset field.
                                                     This value must be a multiple of 0x200. */
#endif
#endif

  uint32_t SystemCoreClock  = 4000000UL ; /*CPU1: M4 on MSI clock after startup (4MHz)*/

  const uint32_t AHBPrescTable[16UL] = {1UL, 3UL, 5UL, 1UL, 1UL, 6UL, 10UL, 32UL, 2UL, 4UL, 8UL, 16UL, 64UL, 128UL, 256UL, 512UL};

  const uint32_t APBPrescTable[8UL]  = {0UL, 0UL, 0UL, 0UL, 1UL, 2UL, 3UL, 4UL};

  const uint32_t MSIRangeTable[16UL] = {100000UL, 200000UL, 400000UL, 800000UL, 1000000UL, 2000000UL, \
                                      4000000UL, 8000000UL, 16000000UL, 24000000UL, 32000000UL, 48000000UL, 0UL, 0UL, 0UL, 0UL}; /* 0UL values are incorrect cases */

#if defined(STM32WB55xx) || defined(STM32WB5Mxx) || defined(STM32WB35xx) || defined (STM32WB15xx) || defined (STM32WB10xx)
  const uint32_t SmpsPrescalerTable[4UL][6UL]={{1UL,3UL,2UL,2UL,1UL,2UL}, \
                                        {2UL,6UL,4UL,3UL,2UL,4UL}, \
                                        {4UL,12UL,8UL,6UL,4UL,8UL}, \
                                        {4UL,12UL,8UL,6UL,4UL,8UL}};
#endif

void SystemInit(void)
{
#if defined(USER_VECT_TAB_ADDRESS)
  /* Configure the Vector Table location add offset address ------------------*/
  SCB->VTOR = VECT_TAB_BASE_ADDRESS | VECT_TAB_OFFSET;
#endif

  /* FPU settings ------------------------------------------------------------*/
  #if (__FPU_PRESENT == 1) && (__FPU_USED == 1)
    SCB->CPACR |= ((3UL << (10UL*2UL))|(3UL << (11UL*2UL)));  /* set CP10 and CP11 Full Access */
  #endif
  
  /* Reset the RCC clock configuration to the default reset state ------------*/
  /* Set MSION bit */
  RCC->CR |= RCC_CR_MSION;

  /* Reset CFGR register */
  RCC->CFGR = 0x00070000U;

  /* Reset PLLSAI1ON, PLLON, HSECSSON, HSEON, HSION, and MSIPLLON bits */
  RCC->CR &= (uint32_t)0xFAF6FEFBU;

  /*!< Reset LSI1 and LSI2 bits */
  RCC->CSR &= (uint32_t)0xFFFFFFFAU;
  
  /*!< Reset HSI48ON  bit */
  RCC->CRRCR &= (uint32_t)0xFFFFFFFEU;
    
  /* Reset PLLCFGR register */
  RCC->PLLCFGR = 0x22041000U;

#if defined(STM32WB55xx) || defined(STM32WB5Mxx)
  /* Reset PLLSAI1CFGR register */
  RCC->PLLSAI1CFGR = 0x22041000U;
#endif
  
  /* Reset HSEBYP bit */
  RCC->CR &= 0xFFFBFFFFU;

  /* Disable all interrupts */
  RCC->CIER = 0x00000000;
}

void SystemCoreClockUpdate(void)
{
  uint32_t tmp, msirange, pllvco, pllr, pllsource , pllm;

  /* Get MSI Range frequency--------------------------------------------------*/

  /*MSI frequency range in Hz*/
  msirange = MSIRangeTable[(RCC->CR & RCC_CR_MSIRANGE) >> RCC_CR_MSIRANGE_Pos];

  /* Get SYSCLK source -------------------------------------------------------*/
  switch (RCC->CFGR & RCC_CFGR_SWS)
  {
    case 0x00:   /* MSI used as system clock source */
      SystemCoreClock = msirange;
      break;

    case 0x04:  /* HSI used as system clock source */
      /* HSI used as system clock source */
        SystemCoreClock = HSI_VALUE;
      break;

    case 0x08:  /* HSE used as system clock source */
      SystemCoreClock = HSE_VALUE;
      break;

    case 0x0C: /* PLL used as system clock  source */
      /* PLL_VCO = (HSE_VALUE or HSI_VALUE or MSI_VALUE/ PLLM) * PLLN
         SYSCLK = PLL_VCO / PLLR
         */
      pllsource = (RCC->PLLCFGR & RCC_PLLCFGR_PLLSRC);
      pllm = ((RCC->PLLCFGR & RCC_PLLCFGR_PLLM) >> RCC_PLLCFGR_PLLM_Pos) + 1UL ;

      if(pllsource == 0x02UL) /* HSI used as PLL clock source */
      {
        pllvco = (HSI_VALUE / pllm);
      }
      else if(pllsource == 0x03UL) /* HSE used as PLL clock source */
      {
        pllvco = (HSE_VALUE / pllm);
      }
      else /* MSI used as PLL clock source */
      {
        pllvco = (msirange / pllm);
      }
      
      pllvco = pllvco * ((RCC->PLLCFGR & RCC_PLLCFGR_PLLN) >> RCC_PLLCFGR_PLLN_Pos);
      pllr = (((RCC->PLLCFGR & RCC_PLLCFGR_PLLR) >> RCC_PLLCFGR_PLLR_Pos) + 1UL);
      
      SystemCoreClock = pllvco/pllr;
      break;

    default:
      SystemCoreClock = msirange;
      break;
  }
  
  /* Compute HCLK clock frequency --------------------------------------------*/
  /* Get HCLK1 prescaler */
  tmp = AHBPrescTable[((RCC->CFGR & RCC_CFGR_HPRE) >> RCC_CFGR_HPRE_Pos)];
  /* HCLK clock frequency */
  SystemCoreClock = SystemCoreClock / tmp;

}

