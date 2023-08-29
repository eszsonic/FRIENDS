#define SENSOR	 BIT0								// Button press sensor
#define TIMESTAMP_BUFFER_SIZE	2
#define LED		BIT0
#define TOUCH BIT1

#define UART_CLK 8000000
#define BAUD_RATE 115200
#define BIT_TIME UART_CLK/BAUD_RATE // 9600 Baud, SMCLK=1MHz (1MHz/9600)=104
#define BIT_TIME_5 UART_CLK/(BAUD_RATE*2) // Time for half a bit.

#define ENABLE_SENSORS()     P2IE |= SENSOR|TOUCH
#define DISABLE_SENSORS()     P2IE &= ~(SENSOR|TOUCH); P2IFG &= ~(SENSOR|TOUCH)


//bitbang SPI
#ifndef SPI_GPIO
#define SPI_GPIO
#endif

unsigned char *lltoa(unsigned long num, unsigned char *str, int radix);
unsigned char *lint2hex(unsigned long num, unsigned char *str, int num_digits);
unsigned char *llint2hex(unsigned long long num, unsigned char *str, int num_digits);

char UART_RX();
void UART_TX(unsigned char byte);
void UART_PRINT(unsigned char *string);
void delay_ms(unsigned int milliseconds);

