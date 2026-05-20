#ifndef TOF_H
#define TOF_H

#include <stdint.h>

void    Tof_Init(void);
int16_t Tof_GetDistanceMm(void);  /* returns -1 on error or out of range */

#endif /* TOF_H */
