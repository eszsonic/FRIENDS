/*
 * flash.c
 *
 *  Created on: Jul 2, 2014
 *      Author: Matthew
 */


#include "flash.h"
#include "lighter.h"
#include <msp430g2433.h>


inline unsigned char send_byte(unsigned char byte_value)
{
	char data_buf=0;
	char i;

	__delay_cycles(1);

		//send command
	for (i = 0 ; i < 8 ; i++)
	{

        if ( (byte_value & 0x80) == 0x80 ){
            P1OUT |= SO;
        }
        else{
            P1OUT &= ~SO;
        }

        P1OUT &= ~SCK;
        byte_value = byte_value << 1;

        if ( P1IN & SI ){
            data_buf = (data_buf | (0x80 >> i));
        }
        P1OUT |= SCK;
	}

	return data_buf;
}

unsigned long read_signature()//For Macronix flash should be 00C22013
{
	unsigned long temp;

	P1OUT&=~CS;
	temp=((unsigned long)send_byte(0x9F)<<24);
	temp|=((unsigned long)send_byte(0x00)<<16);
	temp|=((unsigned long)send_byte(0x00)<<8);
	temp|=(unsigned long)send_byte(0x00);
	P1OUT|=CS;

	return temp;
}

char IsFlashBusy()
{
	return status_read()&0x01;
//	unsigned char temp;
//	temp=status_read()&0x01;
//	if(temp)	P1OUT|=1;
//	else		P1OUT&=~1;
//	return temp; //1 - write operation, 0 - not in write operation
}

void write_timestamp(unsigned long address, unsigned char* source)
{
	unsigned long page;
	unsigned int i;

	//Compute page number
	page=address&0xFFFFFF00;

	//wait for flash not to be busy
	while(IsFlashBusy());

	//write enable
	P1OUT &= ~CS;//CS hi
	send_byte(0x06);
	P1OUT |= CS;//CS hi

	//Program page
	P1OUT &= ~CS;//CS hi
	send_byte(0x02);

	//send address
	send_byte((char)(page>>16));
	send_byte((char)(page>>8));
	send_byte((char)(page));

	//send initial FFs to skip over existing data
	for (i = 0; i < (unsigned int)(address-page); i++) send_byte(0xFF);

	//send timestamp (8bytes)
	//for( i = 0; i < 8; i++ ) send_byte(source[i]);
    for( i = 4; i < 8; i++ ) send_byte(source[i]);
    for( i = 0; i < 4; i++ ) send_byte(source[i]);

	P1OUT |= CS;//CS hi

}


void write_flash(unsigned long page, unsigned char* source, unsigned char count)
{
	unsigned char i;

	//wait for flash not to be busy
	while(IsFlashBusy());

	//write enable
	P1OUT &= ~CS;//CS hi
	send_byte(0x06);
	P1OUT |= CS;//CS hi

	//Program page
	P1OUT &= ~CS;//CS hi
	send_byte(0x02);

	//send address
	send_byte((char)(page>>16));
	send_byte((char)(page>>8));
	send_byte((char)(page));

	//send 256 bytes of data :/
	for (i = 0; i < count; i++) 	send_byte(source[i]);

	P1OUT |= CS;//CS hi
}



void chip_erase()
{
	//wait for flash not to be busy
	while (IsFlashBusy());

	//write enable
	P1OUT &= ~CS;//CS hi
	send_byte(0x06);
	P1OUT |= CS;//CS hi

	//chip erase
	P1OUT &= ~CS;//CS hi
	send_byte(0xC7);
	P1OUT |= CS;//CS hi

	while (IsFlashBusy()) P1OUT|=LED; //wait for finish
	P1OUT&=~LED;
}

void deep_power_down()
{
	//wait for flash not to be busy
	while (IsFlashBusy());

	//write enable
	P1OUT &= ~CS;//CS low
	send_byte(0xB9);
	P1OUT |= CS;//CS hi

}

void release_deep_power_down()
{
	//write enable
	P1OUT &= ~CS;//CS low
	send_byte(0xAB);
	P1OUT |= CS;//CS hi

	//Wait 10us (40 cycles at 8Mhz)
	__delay_cycles(40);
}


void read_flash(unsigned long address, unsigned char* dest, unsigned long count)
{
	//volatile char  a, b, c;

	unsigned long i;

	while (IsFlashBusy());

	P1OUT &= ~CS; //CS lo

	//a=(char)(address>>16);
	//b=(char)(address>>8);
	//c=(char)(address);

	send_byte(0x03); //Data read
	send_byte((char)(address>>16));
	send_byte((char)(address>>8));
	send_byte((char)(address));


	for (i = 0; i < count; i++)
	{
		dest[i] = send_byte(0);
	}

	P1OUT |= CS; //CS hi//flash_CS = 1;

}

inline unsigned char status_read(void)
{
	unsigned char temp;

	P1OUT &= ~CS;
	send_byte(0x05); //read status register
	temp=send_byte(0);
	P1OUT |= CS;//CS hi

	//debug
	//if(temp!=0) P1OUT|=1;
	return temp;
}

unsigned long GetFlashPosition()
{

	unsigned long imax = FLASH_SIZE;
	unsigned long imin = 0;
	unsigned long imid;
	unsigned long value;

	// continue searching while [imin,imax] is not empty
	while (imax >= imin)
	{

		// calculate the midpoint, ensure long alignment
		imid = ((imin+imax)/2)&0xFFFFFFFC;
		read_flash(imid, (unsigned char*)&value, sizeof(unsigned long));

		if(value == 0xFFFFFFFF && imax==imin)//we have zeroed in on the empty slot
		{
			//last log found at index imid
			return imid;//return imid;
		}
		// determine which subarray to search
		else if (value != 0xFFFFFFFF)//valid data, search higher
			// change min index to search upper subarray
			imin = imid+4;
		else//no valid data, search lower
			// change max index to search lower subarray
			imax = imid;
	}

	// no data logs have been saved yet
}

inline unsigned char isFlashEnd(unsigned long position)
{
    //Check if the flash is about to overflow (assuming that we need at least 32 bytes )
    if(position<FLASH_SIZE-32)
        return 0;
    else
        return 1;
}

//the conversion buffer located in main()
extern unsigned char timestamp_conv_buffer[9];

void FlashInit()
{
#ifdef SPI_GPIO
	P1DIR &= ~SI;
	P1DIR |= SO|CS|SCK;
	P1OUT |= CS;//put chip select hi
	P1OUT |= SCK; //clock high

	release_deep_power_down();
	//now wait for status to be ok
	while( read_signature() != 0x00C22013) //should be right
	{
		unsigned int temp_sig=read_signature();
		lltoa(temp_sig,timestamp_conv_buffer,16);
		UART_PRINT("Flash signature incorrect: ");
		UART_PRINT(timestamp_conv_buffer);
		UART_PRINT("\r\n");
	}
#endif

#ifdef SPI_USI
#endif
}
