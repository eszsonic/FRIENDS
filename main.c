//***************************************************************************************
//  MSP430 Serial Flash Data Logger
//
//  M. Bries
//  Texas Instruments, Inc
//  July 2014
//  Built with Code Composer Studio v5
//***************************************************************************************

//use bit banging SPI
#include "flash.h"
#include "lighter.h"
#include <msp430.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

//Defines for event types
#define PUFF_ON  0x1000000000000000
#define PUFF_OFF 0x2000000000000000
#define TOUCH_ON 0x3000000000000000
#define TOUCH_OFF 0x4000000000000000
#define TEMPERATURE_ON 0x5000000000000000
#define TEMPERATUR_OFF 0x6000000000000000
#define READ_TIME 0xE000000000000000
#define SET_TIME 0xF000000000000000

#define MAX_TIME_VALUE 0x00FFFFFFFFFFFFFF

//Define for LED
#define USE_LED

// Globals for half-duplex UART communication
unsigned int TXByte;    // Value sent over UART when Transmit() is called
unsigned int RXByte;    // Value recieved once hasRecieved is set

bool rxReady;   // Lets the program know when a byte is received
bool rfWriteToFlash = false;
bool touchWriteToFlash = false;

//Keeps UNIX timestamp
volatile unsigned long time;


//Only hold one timestamp at a time
volatile unsigned long long puff_start_timestamp=0;
volatile unsigned long long last_pulse_timestamp=MAX_TIME_VALUE;
volatile unsigned long long touch_start_timestamp=0;
volatile unsigned long long touch_end_timestamp=MAX_TIME_VALUE;

volatile unsigned long long current_time=0;


volatile unsigned long flash_position = 0;

unsigned char timestamp_conv_buffer[20];
unsigned char ticks_conv_buffer[5];

//initialize variables
volatile unsigned char first_edge_flag=0;
unsigned int eighth_counter=0;


//interrupt for touch sensor and RF sensor
//RF sensor not implemented yet
#pragma vector = PORT2_VECTOR
__interrupt void Port_2(void)
{
    _DINT();

    //If interrupt is from the RF sensor
    if (P2IFG & SENSOR)
    {

        if(first_edge_flag==1) //for 1st falling edge
        {
            first_edge_flag =0;
#ifdef USE_LED
            P1OUT |= LED; // LED is on when button is pressed (port interrupt occurs)
#endif
            puff_start_timestamp=eighth_counter<<13| TAR;
            puff_start_timestamp=puff_start_timestamp|((long long)time<<16);  //64-bit fixed point number
            last_pulse_timestamp=puff_start_timestamp;
        }
        else // for other falling edges except first
        {
            last_pulse_timestamp=eighth_counter<<13|TAR;
            last_pulse_timestamp=last_pulse_timestamp|((long long)time<<16);  //64-bit fixed point number

        }

        P2IFG &= ~SENSOR;//clear the interrupt flag
    }

    if(P2IFG & TOUCH)
    {
        //check if configured on falling edge, switch
        if(P2IES&TOUCH)//falling edge interrupt
        {
            touch_end_timestamp=eighth_counter<<13| TAR;
            touch_end_timestamp=touch_end_timestamp|((long long)time<<16);  //64-bit fixed point number

            P2IES &= ~TOUCH;//switch to rising edge interrupt

            DISABLE_SENSORS();
            touchWriteToFlash = true;
        }
        else
        {
#ifdef USE_LED
            //P1OUT |= LED; // LED is on when button is pressed (port interrupt occurs)
#endif

            touch_start_timestamp=eighth_counter<<13| TAR;
            touch_start_timestamp=touch_start_timestamp|((long long)time<<16);  //64-bit fixed point number

            P2IES |= TOUCH;//switch to falling edge interrupt
        }

        P2IFG &= ~TOUCH;//clear the interrupt flag
    }

    _EINT();

    //LPM3_EXIT;//exit low power mode and enable interrupts
}

//RTC Clock
#pragma vector = TIMER0_A0_VECTOR
__interrupt void Timer_A0_ISR(void)
{
    _DINT();
    eighth_counter++;

    //Increment seconds every 8 ticks of the interrupt
    if(eighth_counter==8)
    {
        eighth_counter=0;
        time++;
 //       UART_PRINT(llint2hex(last_pulse_timestamp,timestamp_conv_buffer,16));
 //       UART_PRINT("\r\n");
    }

    current_time = eighth_counter<<13|TAR;
    current_time = current_time|((long long)time<<16);


    //If there are detected pulses
    if(first_edge_flag==0)
    {
        if( current_time > (last_pulse_timestamp + 0x4000))
        {
            DISABLE_SENSORS();
            rfWriteToFlash=true;

//        UART_PRINT(llint2hex(puff_start_timestamp,timestamp_conv_buffer,16));
//        UART_PRINT("\r\n");
//        UART_PRINT(llint2hex(last_pulse_timestamp,timestamp_conv_buffer,16));
//        UART_PRINT("\r\n");
//        UART_PRINT(llint2hex(current_time,timestamp_conv_buffer,16));
//        UART_PRINT("\r\n");
        }


    }
    else
    {
        rfWriteToFlash=false;
    }



    _EINT();
    LPM3_EXIT;
}

int main(void) {

    unsigned long i;
    //volatile char a,b,c,d;
    volatile unsigned long temp;

    //volatile unsigned int i;  // volatile to prevent optimization
    WDTCTL = WDTPW | WDTHOLD;       // Stop watchdog timer

    //P1 -
    P1DIR = 0x0;
    P1DIR |= LED ;                  // Set P1.0 for output direction
    //P1OUT = 0xFFFF;
    P1OUT &= ~LED;

    //Sensor inputs
    //P2DIR = 0xFFFF;
    //Touch
    P2DIR &= ~(SENSOR|TOUCH);
    P2OUT = 0x0;

    //Set up the io interrupt for the sensor on P2.0
    P2IES |= SENSOR;//falling edge interrupt
    P2IES &= ~TOUCH;//rising edge interrupt

    P2IFG &= ~(SENSOR|TOUCH);//clear the interrupt flag
    P2IE |= SENSOR|TOUCH;//enable interrupt

    //Set up the UART pins
    P1SEL = BIT1 + BIT2;               // P1.1 = RXD, P1.2=TXD
    P1SEL2 = BIT1 + BIT2;                     // P1.4 = SMCLK, others GPIO

    //Configure UART
    UCA0CTL1 |= UCSSEL_2;                     // SMCLK
    UCA0MCTL = 0xAA;                             //Modulation
    UCA0BR0 = 0x45;                              // 8MHz 115200
    UCA0BR1 = 0;                              // 8MHz 115200
    UCA0MCTL = UCBRS2 + UCBRS0;               // Modulation UCBRSx = 5
    UCA0CTL1 &= ~UCSWRST;                     // **Initialize USCI state machine**
    IE2 |= UCA0RXIE;                          // Enable USCI_A0 RX interrupt


    //Clock config: 8Mhz MCLK from calibrated DCO
    //32Khz XT1 ACLK
    DCOCTL = CALDCO_8MHZ;
    BCSCTL1 = CALBC1_8MHZ;
    BCSCTL3 |= XCAP_3;//xtal has 12.5pF caps

    //Configure 32768Hz Clock
    P2SEL |= (BIT6 | BIT7); // Set P2.6 and P2.6 SEL for XIN, XOUT
    P2SEL2 &= ~(BIT6|BIT7); // Set P2.6 and P2.7 SEL2 for XIN, XOUT
    /* Select 32kHz Crystal for ACLK */
    BCSCTL1 &= (~XTS); // ACLK = LFXT1CLK
    BCSCTL3 &= ~(BIT4|BIT5); // 32768Hz crystal on LFXT1

    //setup timer A for RTC on 32.768kHz watch crystal
    //8Hz interrupts
    //select ACLK as source, Up mode, clear, divider of 1
    //clear interrupt flag
    //enable CCR0
    TACCR0 = 4095;
    TA0CTL = TASSEL_1 + MC_1 + TACLR;
    TA0CTL &= ~TAIFG; TA0CCTL0 = CCIE;


    //Verify LED operation
    P1OUT |= LED;
    delay_ms(1000);
    P1OUT &= ~LED;


    FlashInit();
    flash_position=GetFlashPosition();//gets position in flash memory
    deep_power_down(); //reduce flash power

    //enable interrupts
    _EINT();

    //main body
    first_edge_flag=1;

    while (1)
    {
        LPM3;

        if (rfWriteToFlash==true)
        {
            DISABLE_SENSORS();
            rfWriteToFlash=false;


            UART_PRINT("Puff\r\n");

            //Check if at the end of flash
            if(!isFlashEnd(flash_position))
            {



                release_deep_power_down();

                //Write EVENT_CODE + POSIX times + TAR
                puff_start_timestamp=puff_start_timestamp|PUFF_ON;
                write_timestamp(flash_position, (unsigned char *)&puff_start_timestamp);
                flash_position+=2*sizeof(unsigned long);

                last_pulse_timestamp=last_pulse_timestamp|PUFF_OFF;
                write_timestamp(flash_position, (unsigned char *)&last_pulse_timestamp);
                flash_position+=2*sizeof(unsigned long);

                deep_power_down();
            }

#ifdef USE_LED
            P1OUT &=~ LED;
#endif
            last_pulse_timestamp=MAX_TIME_VALUE;
            first_edge_flag=1;

            ENABLE_SENSORS();
        }

        if (touchWriteToFlash==true)
        {
            DISABLE_SENSORS();
            touchWriteToFlash=false;


            UART_PRINT("Touch\r\n");

            //Check if at the end of flash
            if(!isFlashEnd(flash_position))
            {

                release_deep_power_down();

                //Write EVENT_CODE + POSIX times + TAR
                touch_start_timestamp=touch_start_timestamp|TOUCH_ON;
                write_timestamp(flash_position, (unsigned char *)&touch_start_timestamp);
                flash_position+=2*sizeof(unsigned long);

                touch_end_timestamp=touch_end_timestamp|TOUCH_OFF;
                write_timestamp(flash_position, (unsigned char *)&touch_end_timestamp);
                flash_position+=2*sizeof(unsigned long);

                deep_power_down();
            }
#ifdef USE_LED
            //P1OUT &=~ LED;
#endif
            ENABLE_SENSORS();
        }


        switch(UART_RX())
            {

            case 'm':
                UART_PRINT("Input Command: r = read log, e = erase flash, sXXXXXXXXTTTT = set time, t = read internal time, b = run down the battery\r\n");
                break;

            case 'r':

                DISABLE_SENSORS();
                release_deep_power_down();

                //Capture time of the sensor read
                unsigned long long temp = current_time|READ_TIME;
                write_timestamp(flash_position, (unsigned char *)&temp);
                flash_position+=2*sizeof(unsigned long);

                char message[30];
                sprintf(message,"Number of records: %x\r\n", (flash_position-8)>>4);
                UART_PRINT(message);

                UART_PRINT("Timestamps:\r\n");
                for (i = 0; i < flash_position; i+=8)
                    {
                    unsigned long temp_time;
                    read_flash(i, (unsigned char *)&temp_time, sizeof(unsigned long));
                    //lltoa(temp_time,timestamp_conv_buffer,16);
                    lint2hex(temp_time,timestamp_conv_buffer,8);
                    UART_PRINT(timestamp_conv_buffer);


                    //UART_PRINT(" ");
                    read_flash(i+4,(unsigned char *)&temp_time, sizeof(unsigned long));
                    //lltoa(temp_time,timestamp_conv_buffer,16);
                    lint2hex(temp_time,timestamp_conv_buffer,8);
                    UART_PRINT(timestamp_conv_buffer);
                    UART_PRINT("\r\n");
                    }

                deep_power_down();
                ENABLE_SENSORS();
                break;

            case 'e':
                DISABLE_SENSORS();

                UART_PRINT("Erasing is irreversible! Please confirm (y)\r\n");
                while(!rxReady);
                    if(UART_RX()=='y')
                    {
                        //Erase flash here
                        UART_PRINT("Erasing flash...\r\n");
                        release_deep_power_down();
                        chip_erase();
                        flash_position=0;
                        deep_power_down();

                        UART_PRINT("Finished!\r\n");
                    }
                    else UART_PRINT("Erase cancelled\r\n");

                ENABLE_SENSORS();

            break;

            case 'b':

                DISABLE_SENSORS();

                UART_PRINT("Running down the battery may take a long time! Please confirm (y)\r\n");
                while(!rxReady);
                    if(UART_RX()=='y')
                    {

                        //LED ON
                        P1OUT |= LED;
                        //Print messages
                        UART_PRINT("Disconnect USB and keep disconnected until green LED is off\r\n");
                        while(1);

                    }
                    else UART_PRINT("Run down cancelled\r\n");
               ENABLE_SENSORS();

            break;
            case 's':

                    //store the tick count at which the command was received

                    DISABLE_SENSORS();

                    while(!rxReady);
                    timestamp_conv_buffer[0]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[1]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[2]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[3]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[4]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[5]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[6]=UART_RX();
                    while(!rxReady);
                    timestamp_conv_buffer[7]=UART_RX();
                    timestamp_conv_buffer[8]=0;

                    while(!rxReady);
                    ticks_conv_buffer[0]=UART_RX();
                    while(!rxReady);
                    ticks_conv_buffer[1]=UART_RX();
                    while(!rxReady);
                    ticks_conv_buffer[2]=UART_RX();
                    while(!rxReady);
                    ticks_conv_buffer[3]=UART_RX();
                    ticks_conv_buffer[4]=0;

                    unsigned long temp_time;
                    int temp_ticks;
                    temp_time=strtol(timestamp_conv_buffer,0,16);
                    temp_ticks=(int)strtol(ticks_conv_buffer,0,16);


                    //Adjust time variables
                    TAR=temp_ticks/8;
                    eighth_counter=temp_ticks>>13;
                    time=temp_time;
                    current_time = eighth_counter<<13|TAR;
                    current_time = current_time|((long long)time<<16);

                    //debug
                    UART_PRINT("Set time: ");
                    timestamp_conv_buffer[8]=0; //termination
                    //UART_PRINT(lltoa(time,timestamp_conv_buffer,16));
                    UART_PRINT(lint2hex(time,timestamp_conv_buffer,8));
                    UART_PRINT(" ");
                    ticks_conv_buffer[4]=0;
                    //UART_PRINT(lltoa(temp_ticks,ticks_conv_buffer,16));
                    UART_PRINT(lint2hex(temp_ticks,ticks_conv_buffer,4));
                    UART_PRINT("\r\n");

                    //write time to flash

                    release_deep_power_down();
                    unsigned long long temp_timestamp = current_time|SET_TIME;
                    write_timestamp(flash_position, (unsigned char *)&temp_timestamp);
                    flash_position+=2*sizeof(unsigned long);
                    deep_power_down();

                    ENABLE_SENSORS();

                    break;

            case 't':

                    DISABLE_SENSORS();
                    //ltoa(time,time_buffer,16);
                    UART_PRINT("Internal timestamp: ");
                    UART_PRINT(lint2hex(time,timestamp_conv_buffer,8));
                    UART_PRINT(" ");
                    UART_PRINT(lint2hex(eighth_counter<<13|TAR,ticks_conv_buffer,4));
                    UART_PRINT("\r\n");

                    ENABLE_SENSORS();

                    break;

            default: break;
            }

        } //while(1)
} //Main()



// UART interrupt
#pragma vector=USCIAB0RX_VECTOR
__interrupt void USCI0RX_ISR(void)
{
  RXByte = UCA0RXBUF;
  rxReady = true;
  //Test loop
  //while (!(IFG2&UCA0TXIFG));                // USCI_A0 TX buffer ready?
  //UCA0TXBUF = UCA0RXBUF;                    // TX -> RXed character
  LPM3_EXIT;//exit low power mode and enable interrupts
}



// Delays by the specified Milliseconds
void delay_ms(unsigned int milliseconds)
{
    unsigned int temp = milliseconds;
    while(temp--)
    {
    //__delay_cycles(16000); // set for 16Mhz change it to 1000 for 1 Mhz
    __delay_cycles(8000); // set for 16Mhz change it to 1000 for 1 Mhz
    }
}


char UART_RX()
{
    char return_byte;
    if(rxReady) { return_byte=RXByte; rxReady=false;}
    else        return_byte=0;
    return return_byte;
}

void UART_TX(unsigned char byte)
{
    while (!(IFG2&UCA0TXIFG));                // USCI_A0 TX buffer ready?
    UCA0TXBUF = byte;                    // TX -> RXed character
}

void UART_PRINT(unsigned char *string) {                 // Prints a string using the Timer_A UART
  while (*string)
    UART_TX(*string++);
}

unsigned char *lltoa(unsigned long num, unsigned char *str, int radix) {

    unsigned long temp_num=num;
    char sign = 0;
    char temp[33];  //an int can only be 32 bits long
                    //at radix 2 (binary) the string
                    //is at most 16 + 1 null long.
    int temp_loc = 0;
    int digit;
    int str_loc = 0;

    //save sign for radix 10 conversion
    if (radix == 10 && num < 0) {
        sign = 1;
        num = -num;
    }

    //construct a backward string of the number.
    do {
        digit = temp_num % radix;
        if (digit < 10)
            temp[temp_loc++] = digit + '0';
        else
            temp[temp_loc++] = digit - 10 + 'A';
        temp_num /= radix;
    } while (temp_num > 0);

    //now add the sign for radix 10
    if (radix == 10 && sign) {
        temp[temp_loc] = '-';
    } else {
        temp_loc--;
    }


    //now reverse the string.
    while ( temp_loc >=0 ) {// while there are still chars
        str[str_loc++] = temp[temp_loc--];
    }
    str[str_loc] = 0; // add null termination.

    return str;
}

const unsigned char conversion_table[]={'0','1','2','3','4','5','6','7','8','9','A','B','C','D','E','F'};

unsigned char *lint2hex(unsigned long num, unsigned char *str, int num_digits) {

    unsigned long temp_num=num;

    int i;

    for(i=0; i<num_digits;i++)
    {

        str[num_digits-1-i]=conversion_table[(unsigned char)temp_num&0x0F];
        temp_num=temp_num>>4;
    }

    str[num_digits]=0;

    return str;
}

unsigned char *llint2hex(unsigned long long num, unsigned char *str, int num_digits) {

    unsigned long long temp_num=num;

    int i;

    for(i=0; i<num_digits;i++)
    {

        str[num_digits-1-i]=conversion_table[(unsigned char)temp_num&0x0F];
        temp_num=temp_num>>4;
    }

    str[num_digits]=0;

    return str;
}

