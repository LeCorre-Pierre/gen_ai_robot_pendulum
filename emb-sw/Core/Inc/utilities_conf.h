#ifndef UTILITIES_CONF_H
#define UTILITIES_CONF_H

#include "cmsis_compiler.h"

#define UTILS_ENTER_CRITICAL_SECTION()  __disable_irq()
#define UTILS_EXIT_CRITICAL_SECTION()   __enable_irq()

#endif /* UTILITIES_CONF_H */
