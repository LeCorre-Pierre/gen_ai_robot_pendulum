#include <errno.h>
#include <stdint.h>

void *_sbrk(ptrdiff_t incr)
{
    extern uint8_t _end;
    extern uint8_t _estack;
    extern uint32_t _Min_Stack_Size;
    static uint8_t *heap_end;
    uint8_t *prev_heap_end;

    if (heap_end == 0)
        heap_end = &_end;

    prev_heap_end = heap_end;

    if (heap_end + incr > &_estack - (uint32_t)&_Min_Stack_Size) {
        errno = ENOMEM;
        return (void *)-1;
    }

    heap_end += incr;
    return prev_heap_end;
}
