# GDB debug session for STM32WB5MMG (emb-sw)
# Usage:
#   .\debug-gdb.ps1 server    -> lance le GDB server (Terminal 1)
#   .\debug-gdb.ps1 gdb       -> lance arm-none-eabi-gdb connecté (Terminal 2)

$GDBSERVER = "C:\ST\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_2.2.400.202601091506\tools\bin\ST-LINK_gdbserver.exe"
$CUBEPROG  = "C:\ST\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.win32_2.2.400.202601091506\tools\bin"
$GDB       = "C:\ST\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740\tools\bin\arm-none-eabi-gdb.exe"
$ELF       = "D:\Projects\gen_ai_robot_pendulum\emb-sw\Debug\emb-sw.elf"
$PORT      = 61234

switch ($args[0]) {
    "server" {
        Write-Host "Starting ST-LINK GDB server on port $PORT..."
        & $GDBSERVER -p $PORT -m 0 -k -d -s -v -cp "$CUBEPROG"
    }
    "gdb" {
        Write-Host "Connecting arm-none-eabi-gdb to localhost:$PORT..."
        Write-Host "Commands: target remote localhost:$PORT  |  load  |  break main  |  continue"
        & $GDB $ELF -ex "target remote localhost:$PORT"
    }
    default {
        Write-Host "Usage: .\debug-gdb.ps1 [server|gdb]"
    }
}
