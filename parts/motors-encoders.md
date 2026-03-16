29:1 Metal Gearmotor 37Dx52L mm with 64 CPR Encoder

Reference: http://www.pololu.com/catalog/product/1443

This 2.54" × 1.45" × 1.45" gearmotor is a powerful 12V brushed DC motor with a 29:1 metal gearbox and an integrated quadrature encoder that provides a resolution of 64 counts per revolution of the motor shaft, which corresponds to 1856 counts per revolution of the gearbox’s output shaft. These units have a 0.61"-long, 6 mm-diameter D-shaped output shaft

Key specs at 12 V: 350 RPM and 300 mA free-run, 110 oz-in (8 kg-cm) and 5 A stall.

A two-channel Hall effect encoder is used to sense the rotation of a magnetic disk on a rear protrusion of the motor shaft. The quadrature encoder provides a resolution of 64 counts per revolution of the motor shaft. To compute the counts per revolution of the gearbox output, multiply the gear ratio by 64. The motor/encoder has six color-coded, 11" (28 cm) leads:
Color	Function
Red	motor power (connects to one motor terminal)
Black	motor power (connects to the other motor terminal)
Green	encoder GND
Blue	encoder Vcc (3.5 – 20 V)
Yellow	encoder A output
White	encoder B output
The Hall sensor requires an input voltage, Vcc, between 3.5 and 20 V and draws a maximum of 10 mA. The A and B outputs are square waves from 0 V to Vcc approximately 90° out of phase. The frequency of the transitions tells you the speed of the motor, and the order of the transitions tells you the direction. The following oscilloscope capture shows the A and B (yellow and white) encoder outputs using a motor voltage of 12 V and a Hall sensor Vcc of 5 V:

By counting both the rising and falling edges of both the A and B outputs, it is possible to get 64 counts per revolution of the motor shaft. Using just a single edge of one channel results in 16 counts per revolution of the motor shaft, so the frequency of the A output in the above oscilloscope capture is 16 times the motor rotation frequency.
As of July, 2012, we are shipping these gearmotors with leads terminated by a 1×6 0.1″ female header, as shown in the main product picture. If this header is not convenient for your application, you can pull the crimped wires out of the header or cut the header off. Previously, these gearmotors shipped with stripped, unterminated leads.
