/*
 * flash.h
 *
 *  Created on: Jul 2, 2014
 *      Author: Matthew
 */

#ifndef FLASH_H_
#define FLASH_H_

#define SCK BIT5
#define SO BIT7
#define SI BIT6
#define CS BIT4//chip select
#define FLASH_SIZE	524288 //4Mbit, 524288 bytes

void FlashInit();
unsigned long GetFlashPosition();
inline unsigned char isFlashEnd(unsigned long position);

unsigned long read_signature();
inline unsigned char send_byte(unsigned char byte_value);

void read_flash(unsigned long address, unsigned char* dest, unsigned long count);
void write_flash(unsigned long page, unsigned char* source, unsigned char count);
void write_timestamp(unsigned long address, unsigned char* source);

void sector_erase(unsigned long sector);
void block_erase(unsigned long block);
void chip_erase();
void deep_power_down();
void release_deep_power_down();

unsigned char status_read(void);

#endif /* FLASH_H_ */
