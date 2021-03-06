#!/usr/bin/env python3

"""
ME Analyzer
Intel Engine Firmware Analysis Tool
Copyright (C) 2014-2017 Plato Mavropoulos
"""

title = 'ME Analyzer v1.16.2'

import os
import re
import sys
import lzma
import struct
import ctypes
import shutil
import hashlib
import inspect
import binascii
import tempfile
import colorama
import traceback
import subprocess
import contextlib

# Initialize and setup Colorama
colorama.init()
col_r = colorama.Fore.RED + colorama.Style.BRIGHT
col_c = colorama.Fore.CYAN + colorama.Style.BRIGHT
col_b = colorama.Fore.BLUE + colorama.Style.BRIGHT
col_g = colorama.Fore.GREEN + colorama.Style.BRIGHT
col_y = colorama.Fore.YELLOW + colorama.Style.BRIGHT
col_m = colorama.Fore.MAGENTA + colorama.Style.BRIGHT
col_e = colorama.Fore.RESET + colorama.Style.RESET_ALL

# Detect OS Platform
mea_os = sys.platform
if mea_os == 'win32' :
	cl_wipe = 'cls'
	uf_exec = 'UEFIFind.exe'
	os_dir = '\\'
elif mea_os.startswith('linux') or mea_os == 'darwin' :
	cl_wipe = 'clear'
	uf_exec = 'UEFIFind'
	os_dir = '//'
else :
	print(col_r + '\nError: ' + col_e + 'Unsupported platform: %s\n' % mea_os)
	input('Press enter to exit')
	colorama.deinit()
	sys.exit(-1)

char = ctypes.c_char
uint8_t = ctypes.c_ubyte
uint16_t = ctypes.c_ushort
uint32_t = ctypes.c_uint
uint64_t = ctypes.c_uint64

class MEA_Param :

	def __init__(self, source) :
	
		self.all = ['-?','-skip','-multi','-ubupre','-ubu','-extr','-msg','-hid','-adir','-aecho','-unp86','-dsku','-pdb','-enuf','-dbname','-mass','-dfpt']

		self.win = ['-ubupre','-ubu','-extr','-msg','-hid','-aecho','-adir'] # Windows only
		
		if mea_os == 'win32' :
			self.val = self.all
		else :
			self.val = [item for item in self.all if item not in self.win]
		
		self.help_scr = False
		self.skip_intro = False
		self.multi = False
		self.ubu_mea_pre = False
		self.ubu_mea = False
		self.extr_mea = False
		self.print_msg = False
		self.alt_dir = False
		self.hid_find = False
		self.alt_msg_echo = False
		self.me11_mod_extr = False
		self.me11_sku_disp = False
		self.fpt_disp = False
		self.db_print_new = False
		self.enable_uf = False
		self.give_db_name = False
		self.mass_scan = False
		
		for i in source :
			if i == '-?' : self.help_scr = True # Displays MEA help text for end-users.
			if i == '-skip' : self.skip_intro = True # Skips the MEA options intro screen.
			if i == '-multi' : self.multi = True # Checks multiple files, copies those with messages to new folder.
			if i == '-unp86' : self.me11_mod_extr = True # Fully unpack Engine x86 firmware ($FPT + $CPD).
			if i == '-dsku' : self.me11_sku_disp = True # Forces MEA to print ME x86 Debug SKU detection.
			if i == '-pdb' : self.db_print_new = True # Writes input firmware's DB entries to file.
			if i == '-enuf' : self.enable_uf = True # Enables UEFIFind Engine GUID Detection.
			if i == '-dbname' : self.give_db_name = True # Rename input file based on DB structured name.
			if i == '-mass' : self.mass_scan = True # Scans all files of a given directory, no limit.
			if i == '-dfpt' : self.fpt_disp = True # Displays details about the $FPT header.
			
			if mea_os == 'win32' : # Windows only options
				if i == '-adir' : self.alt_dir = True # Sets UEFIFind to the previous directory.
				if i == '-ubupre' : self.ubu_mea_pre = True # UBU Pre-Menu mode, 9 --> Engine FW found, 8 --> Engine FW not found.
				if i == '-ubu' : self.ubu_mea = True # UBU mode, prints everything without some headers.
				if i == '-extr' : self.extr_mea = True # UEFI Strip mode, prints special one-line outputs.
				if i == '-msg' : self.print_msg = True # Prints all messages without any headers.
				if i == '-hid' : self.hid_find = True # Forces MEA to display any firmware found. Works with -msg.
				if i == '-aecho' : self.alt_msg_echo = True # Enables an alternative display of empty lines. Works with -msg and -hid.
			
		if self.ubu_mea_pre or self.ubu_mea or self.extr_mea or self.print_msg or self.mass_scan \
		or self.db_print_new : self.skip_intro = True

# Engine Structures
class FPT_Pre_Header(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("ROMB_Instr_0",	uint32_t),		# 0x00
		("ROMB_Instr_1",	uint32_t),		# 0x04
		("ROMB_Instr_2",	uint32_t),		# 0x08
		("ROMB_Instr_3",	uint32_t),		# 0x0C
		# 0x10
	]

# noinspection PyTypeChecker
class FPT_Header(ctypes.LittleEndianStructure) : # Flash Partition Table
	_pack_ = 1
	_fields_ = [
		("Tag",				char*4),		# 0x00
		("NumPartitions",	uint32_t),		# 0x04
		("Version",			uint8_t),		# 0x08
		("EntryType",		uint8_t),		# 0x09
		("Length",			uint8_t),		# 0x0A
		("Checksum",		uint8_t),		# 0x0B
		("FlashCycleLife",	uint16_t),		# 0x0C
		("FlashCycleLimit",	uint16_t),		# 0x0E
		("UMASize",			uint32_t),		# 0x10
		("Flags",			uint32_t),		# 0x14
		("FitMajor",		uint16_t),		# 0x18
		("FitMinor",		uint16_t),		# 0x1A
		("FitHotfix",		uint16_t),		# 0x1C
		("FitBuild",		uint16_t),		# 0x1E
		# 0x20
	]

# noinspection PyTypeChecker
class FPT_Entry(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*4),		# 0x00
		("Owner",			char*4),		# 0x04
		("Offset",			uint32_t),		# 0x08
		("Size",			uint32_t),		# 0x0C
		("StartTokens",		uint32_t),		# 0x10
		("MaxTokens",		uint32_t),		# 0x14
		("ScratchSectors",	uint32_t),		# 0x18
		("Flags",			uint32_t),		# 0x1C
		# 0x20
	]

# noinspection PyTypeChecker
class MN2_Manifest(ctypes.LittleEndianStructure) : # Manifest ($MAN/$MN2)
	_pack_ = 1
	_fields_ = [
		("Type",			uint32_t),		# 0x00
		("HeaderLength",	uint32_t),		# 0x04 (*4)
		("HeaderVersion",	uint32_t),		# 0x08
		("Flags",			uint32_t),		# 0x0C
		("VEN_ID",			uint32_t),		# 0x10 (0x8086)
		("Day",				uint8_t),		# 0x14
		("Month",			uint8_t),		# 0x15
		("Year",			uint16_t),		# 0x16
		("Size",			uint32_t),		# 0x18 (*4)
		("Tag",				char*4),		# 0x1C
		("NumModules",		uint32_t),		# 0x20 (Reserved at $CPD)
		("Major",			uint16_t),		# 0x24
		("Minor",			uint16_t),		# 0x26
		("Hotfix",			uint16_t),		# 0x28
		("Build",			uint16_t),		# 0x2A
		("SVN_9",			uint8_t),		# 0x2C (ME9+)
		("Reserved0",		uint8_t*3),		# 0x2D
		("SVN_8",			uint8_t),		# 0x30 (ME8, Reserved at $CPD)
		("Reserved1",		uint8_t*3),		# 0x31
		("VCN",				uint8_t),		# 0x34 (ME8-10, Reserved at $CPD)
		("Reserved2",		uint8_t*3),		# 0x35
		("Reserved3",		uint32_t*16),	# 0x38
		("KeySize",			uint32_t),		# 0x78
		("ScratchSize",		uint32_t),		# 0x7C
		("RsaPubKey",		uint32_t*64),	# 0x80
		("RsaPubExp",		uint32_t),		# 0x180
		("RsaSig",			uint32_t*64),	# 0x184
		# 0x284
	]

# noinspection PyTypeChecker
class MME_Header_Old(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Tag",				char*4),		# 0x00
		("Guid",			uint8_t*16),	# 0x04
		("MajorVersion",	uint16_t),		# 0x14
		("MinorVersion",	uint16_t),		# 0x16
		("HotfixVersion",	uint16_t),		# 0x18
		("BuildVersion",	uint16_t),		# 0x1A
		("Name",			char*16),		# 0x1C
		("Hash",			uint8_t*20),	# 0x2C
		("Size",			uint32_t),		# 0x40
		("Flags",			uint32_t),		# 0x44
		("Unk48_4C",		uint32_t),		# 0x48
		("Unk4C_50",		uint32_t),		# 0x4C
		# 0x50
	]

# noinspection PyTypeChecker
class MME_Header_New(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Tag",				char*4),		# 0x00
		("Name",			char*16),		# 0x04
		("Hash",			uint8_t*32),	# 0x14
		("ModBase",			uint32_t),		# 0x34
		("Offset_MN2",		uint32_t),		# 0x38 (from $MN2)
		("SizeUncomp",		uint32_t),		# 0x3C
		("SizeComp",		uint32_t),		# 0x40
		("MemorySize",		uint32_t),		# 0x44
		("PreUmaSize",		uint32_t),		# 0x48
		("EntryPoint",		uint32_t),		# 0x4C
		("Flags",			uint32_t),		# 0x50
		("Unk54",			uint32_t),		# 0x54
		("Unk58",			uint32_t),		# 0x58
		("Unk5C",			uint32_t),		# 0x5C
		# 0x60
	]

# noinspection PyTypeChecker
class MCP_Header(ctypes.LittleEndianStructure) : # Multi Chip Package
	_pack_ = 1
	_fields_ = [
		("Tag",				char*4),		# 0x00
		("HeaderSize",		uint32_t),		# 0x04 (*4)
		("CodeSize",		uint32_t),		# 0x08
		("Offset_Code_MN2",	uint32_t),		# 0x0C (Code start from $MN2)
		("Offset_Part_FPT",	uint32_t),  	# 0x10 (Partition start from $FPT)
		("Hash",			uint8_t*32),	# 0x14
		("Unknown34_38", 	uint32_t),  	# 0x34
		("Unknown38_3C", 	uint32_t),  	# 0x38 (ME8+)
		("Unknown3C_40", 	uint32_t),  	# 0x3C (ME8+)
		("Unknown40_44", 	uint32_t),  	# 0x40 (ME8+)
		# 0x38 ME7, 0x44 ME8+
	]

# noinspection PyTypeChecker
class CPD_Header(ctypes.LittleEndianStructure) : # Code Partition Directory
	_pack_ = 1
	_fields_ = [
		("Tag",				char*4),		# 0x00
		("NumModules",		uint32_t),		# 0x04
		("HeaderVersion",	uint8_t),		# 0x08
		("EntryVersion",	uint8_t),		# 0x09
		("HeaderLength",	uint8_t),		# 0x0A
		("Checksum",		uint8_t),		# 0x0B
		("PartitionName",	char*4),		# 0x0C
		# 0x10
	]

# noinspection PyTypeChecker
class CPD_Entry(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*12),		# 0x00
		("OffsetAttrib",	uint32_t),		# 0x0C (LE --> 0:24 Offset from $CPD, 25 Compressed No/Yes, 26:31 Reserved)
		("Size",			uint32_t),		# 0x10 (Uncompressed for LZMA/Huffman, Compressed at CPD_Ext_0A instead)
		("Reserved",		uint32_t),		# 0x14
		# 0x18
	]

# noinspection PyTypeChecker
class CPD_Ext_00(ctypes.LittleEndianStructure) : # System Info
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("MinUMASize",		uint32_t),		# 0x08
		("ChipsetVersion",	uint32_t),		# 0x0C
		("IMGDefaultHash",	uint32_t*8),	# 0x10
		("PageableUMASize",	uint32_t),		# 0x30
		("Reserved0",		uint64_t),		# 0x34
		("Reserved1",		uint32_t),		# 0x3C
		# 0x40
	]
	
# noinspection PyTypeChecker
class CPD_Ext_00_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*4),		# 0x00
		("Version",			uint32_t),		# 0x04
		("UserID",			uint16_t),		# 0x08
		("Reserved",		uint16_t),		# 0x0A
		# 0x0C
	]
	
# noinspection PyTypeChecker
class CPD_Ext_01(ctypes.LittleEndianStructure) : # Init Script
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("Reserved",		uint32_t),		# 0x08
		("ModuleCount",		uint32_t),		# 0x0C
		# 0x10
	]
	
# noinspection PyTypeChecker
class CPD_Ext_01_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("PartitionName",	char*4),		# 0x00
		("ModuleName",		char*12),		# 0x0C
		("InitFlowFlags",	uint32_t),		# 0x10
		("BootTypeFlags",	uint32_t),		# 0x14 (LE --> 0 Normal, 1 HAP, 2 HMRFPO, 3 Temp Disable, 4 Recovery, 5 Safe Mode, 6 FW Update, 7:31 Reserved)
		# 0x18
	]
	
# noinspection PyTypeChecker
class CPD_Ext_02(ctypes.LittleEndianStructure) : # Feature Permissions
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("FeatureCount",	uint32_t),		# 0x08
		# 0x0C
	]

# noinspection PyTypeChecker
class CPD_Ext_02_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("UserID",			uint16_t),		# 0x00
		("Reserved",		uint16_t),		# 0x02
		# 0x04
	]
	
# noinspection PyTypeChecker
class CPD_Ext_03(ctypes.LittleEndianStructure) : # Partition Info
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("PartitionName",	char*4),		# 0x08
		("PartitionSize",	uint32_t),		# 0x0C
		("Hash",			uint32_t*8),	# 0x10
		("VCN",				uint32_t),		# 0x30
		("PartitionVer",	uint32_t),  	# 0x34
		("DataFormatVer", 	uint32_t),  	# 0x38
		("InstanceID", 		uint32_t),  	# 0x3C
		("Flags", 			uint32_t),  	# 0x40
		("Reserved", 		uint32_t*5),  	# 0x40
		# 0x58
	]
	
# noinspection PyTypeChecker
class CPD_Ext_03_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*12),		# 0x00
		("Type",			uint8_t),		# 0x0C (0 Process, 1 Shared Library, 2 Data)
		("Compression",		uint8_t),		# 0x0D (0 Uncompressed --> always, 1 Huffman, 2 LZMA)
		("Reserved",		uint16_t),		# 0x0E (FFFF)
		("MetadataSize",	uint32_t),		# 0x10
		("MetadataHash",	uint32_t*8),	# 0x14
		# 0x34
	]
	
# noinspection PyTypeChecker
class CPD_Ext_04(ctypes.LittleEndianStructure) : # Shared Lib
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("ContextSize",		uint32_t),		# 0x08
		("TotAlocVirtSpc",	uint32_t),		# 0x0C
		("CodeBaseAddress",	uint32_t),		# 0x10
		("TLSSize",			uint32_t),		# 0x14
		("Reserved",		uint32_t),		# 0x18
		# 0x1C
	]
	
# noinspection PyTypeChecker
class CPD_Ext_05(ctypes.LittleEndianStructure) : # Process Manifest
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("Flags",			uint32_t),		# 0x08
		("CodeBaseAddress",	uint32_t),		# 0x0C
		("CodeSizeUncomp",	uint32_t),		# 0x10
		("CM0HeapSize",		uint32_t),		# 0x14
		("BSSSize",			uint32_t),		# 0x18
		("DefaultHeapSize",	uint32_t),		# 0x1C
		("MainThreadEntry",	uint32_t),		# 0x20
		("AllowedSysCalls",	uint32_t*3),	# 0x24
		("UserID",			uint16_t),		# 0x30
		("Reserved0",		uint32_t),		# 0x32
		("Reserved1",		uint16_t),		# 0x36
		("Reserved2",		uint64_t),		# 0x38
		("GroupID",			uint16_t*3),	# 0x40
		# 0x46
	]
	
# noinspection PyTypeChecker
class CPD_Ext_06(ctypes.LittleEndianStructure) : # Threads
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		# 0x08
	]
		
# noinspection PyTypeChecker
class CPD_Ext_06_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("StackSize",		uint32_t),		# 0x00
		("Flags",			uint32_t),		# 0x04
		("SchedulPolicy",	uint32_t),		# 0x08
		("Reserved",		uint32_t),		# 0x0C
		# 0x10
	]
	
# noinspection PyTypeChecker
class CPD_Ext_07(ctypes.LittleEndianStructure) : # Device IDs
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		# 0x08
	]

# noinspection PyTypeChecker
class CPD_Ext_07_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("DeviceID",		uint32_t),		# 0x00
		("Reserved",		uint32_t),		# 0x04
		# 0x08
	]
	
# noinspection PyTypeChecker
class CPD_Ext_08(ctypes.LittleEndianStructure) : # MMIO Ranges
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		# 0x8
	]
	
# noinspection PyTypeChecker
class CPD_Ext_08_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("BaseAddress",		uint32_t),		# 0x00
		("SizeLimit",		uint32_t),		# 0x04
		("Flags",			uint32_t),		# 0x08
		# 0x0C
	]

# noinspection PyTypeChecker
class CPD_Ext_09(ctypes.LittleEndianStructure) : # Special File Producer
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("MajorNumber",		uint16_t),		# 0x08
		("Flags",			uint16_t),		# 0x0A
		# 0x0C
	]
	
# noinspection PyTypeChecker
class CPD_Ext_09_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*12),		# 0x00
		("AccessMode",		uint16_t),		# 0x0C
		("UserID",			uint16_t),		# 0x0E
		("GroupID",			uint16_t),		# 0x10
		("MinorNumber",		uint8_t),		# 0x12
		("Reserved0",		uint8_t),		# 0x13
		("Reserved1",		uint32_t),		# 0x14
		# 0x18
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0A(ctypes.LittleEndianStructure) : # Module Attributes
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("Compression",		uint8_t),		# 0x08 (0 Uncompressed, 1 Huffman, 2 LZMA)
		("Encryption",		uint8_t),		# 0x09 (0 No, 1 Yes, unknown if LE MSB or entire Byte)
		("Reserved0",		uint8_t),		# 0x0A
		("Reserved1",		uint8_t),		# 0x0B
		("SizeUncomp",		uint32_t),		# 0x0C
		("SizeComp",		uint32_t),		# 0x10 (LZMA & Huffman w/o EOM alignment)
		("DEV_ID",			uint16_t),		# 0x14
		("VEN_ID",			uint16_t),		# 0x16 (0x8086)
		("Hash",			uint32_t*8),	# 0x18 (Compressed for LZMA, Uncompressed for Huffman)
		# 0x38
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0B(ctypes.LittleEndianStructure) : # Locked Ranges
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		# 0x08
	]

# noinspection PyTypeChecker
class CPD_Ext_0B_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("RangeBase",		uint32_t),		# 0x00
		("RangeSize",		uint32_t),		# 0x04
		# 0x08
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0C(ctypes.LittleEndianStructure) : # Client System Info
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("FWSKUCaps",		uint32_t),		# 0x08
		("FWSKUCapsReserv",	uint32_t*7),	# 0x0C
		("FWSKUAttrib",		uint64_t),		# 0x28
		# 0x30
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0D(ctypes.LittleEndianStructure) : # User Info (vfs)
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		# 0x8
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0D_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("UserID",			uint16_t),		# 0x00
		("Reserved",		uint16_t),		# 0x02
		("NVStorageQuota",	uint32_t),		# 0x04
		("RAMStorageQuota",	uint32_t),		# 0x08
		("WOPQuota",		uint32_t),		# 0x0C
		("WorkingDir",		uint32_t*9),	# 0x10
		# 0x44
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0E(ctypes.LittleEndianStructure) : # Key Manifest (TXE)
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("Unknown08_0C",	uint32_t),		# 0x08
		("Unknown0C_24",	uint32_t*6),	# 0x0C
		# 0x24
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0E_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Unknown00_04",	uint32_t),		# 0x00
		("Unknown04_20",	uint32_t*7),	# 0x04
		("Unknown20_24",	uint32_t*7),	# 0x20
		("Unknown24_44",	uint32_t*7),	# 0x24 (SHA256 Hash)
		# 0x44
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0F(ctypes.LittleEndianStructure) : # Package Info (TXE)
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("PartitionName",	char*4),		# 0x08
		("VCN",				uint32_t),		# 0x0C
		("UsageBitmap",		uint32_t*4),	# 0x10
		("SVN",				uint32_t),		# 0x20
		("Reserved",		uint32_t*4),  	# 0x24
		# 0x34
	]
	
# noinspection PyTypeChecker
class CPD_Ext_0F_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Name",			char*12),		# 0x00
		("Type",			uint8_t),		# 0x0C (0 Process, 1 Shared Library, 2 Data, 3 TBD)
		("HashAlgorithm",	uint8_t),		# 0x0D (0 Reserved, 1 SHA1, 2 SHA256)
		("HashSize",		uint16_t),		# 0x0E (0x20, only SHA256 for BXT)
		("MetadataSize",	uint32_t),		# 0x10
		("MetadataHash",	uint32_t*8),	# 0x14
		# 0x34
	]
	
# noinspection PyTypeChecker
class CPD_Ext_12(ctypes.LittleEndianStructure) : # ??? (TXE)
	_pack_ = 1
	_fields_ = [
		("Tag",				uint32_t),		# 0x00
		("Size",			uint32_t),		# 0x04
		("ModuleCount",		uint32_t),		# 0x08
		("Reserved",		uint32_t*4),	# 0x0C
		# 0x1C
	]
	
# noinspection PyTypeChecker
class CPD_Ext_12_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Unknown00_04",	uint32_t),		# 0x00
		("Unknown04_08",	uint32_t),		# 0x04
		("Unknown08_0C",	uint32_t),		# 0x08
		("Unknown0C_10",	uint32_t),		# 0x0C
		("Unknown10_18",	uint32_t*2),	# 0x10 (FFFFFFFFFFFFFFFF)
		("Unknown18_1C",	uint32_t),		# 0x18
		("Unknown1C_20",	uint32_t),		# 0x1C
		("Unknown20_28",	uint32_t*2),	# 0x20 (FFFFFFFFFFFFFFFF)
		("Unknown28_2C",	uint32_t),		# 0x28
		("Unknown2C_30",	uint32_t),		# 0x2C
		("Unknown30_38",	uint32_t*2),	# 0x30 (FFFFFFFFFFFFFFFF)
		# 0x38
	]
	
# noinspection PyTypeChecker
class CPD_Ext_15(ctypes.LittleEndianStructure) : # Secure Token (TXE, no sample)
	_pack_ = 1
	_fields_ = [
		("Unknown00_04",	uint32_t),		# 0x00
		# 0x??
	]
	
# noinspection PyTypeChecker
class CPD_Ext_15_Mod(ctypes.LittleEndianStructure) :
	_pack_ = 1
	_fields_ = [
		("Unknown00_04",	uint32_t),		# 0x00
		# 0x??
	]
	
# Inspired from Igor Skochinsky's me_unpack
def get_struct(str_, off, struct):
	my_struct = struct()
	struct_len = ctypes.sizeof(my_struct)
	str_data = str_[off:off + struct_len]
	fit_len = min(len(str_data), struct_len)
	
	if (off > file_end) or (fit_len < struct_len) :
		err_stor.append(col_r + "Error: Offset 0x%0.2X out of bounds, possibly incomplete image!" % off + col_e)
		
		for error in err_stor : print(error)
		
		if param.multi : multi_drop()
		else: f.close()
		
		mea_exit(1)
	
	
	ctypes.memmove(ctypes.addressof(my_struct), str_data, fit_len)
	
	return my_struct

# MEA Version Header
def mea_hdr_init() :
	if not param.extr_mea and not param.print_msg :
		db_rev = "None"
		try :
			fw_db = db_open()
			for line in fw_db :
				if 'Revision' in line :
					db_line = line.split()
					db_rev = db_line[2]
			fw_db.close()
		except :
			pass
			
		return db_rev

def mea_hdr(db_rev) :	
	print("\n-------[ %s ]-------" % title)
	print("            Database %s" % db_rev)
		
def mea_help() :
	
	text = "\nUsage: MEA [FilePath] {Options}\n\n{Options}\n\n"
	text += "-?      : Displays help & usage screen\n"
	text += "-skip   : Skips options intro screen\n"
	text += "-multi  : Scans multiple files and copies on messages\n"
	text += "-mass   : Scans all files of a given directory\n"
	text += "-enuf   : Enables UEFIFind Engine GUID detection\n"
	text += "-pdb    : Writes input firmware's DB entries to file\n"
	text += "-dbname : Renames input file based on DB name\n"
	text += "-dfpt   : Shows info about the $FPT header (Research)\n"
	text += "-dsku   : Shows verbose info for ME 11+ SKU (Research)\n"
	text += "-unp86  : Unpacks fully all Engine x86 firmware (Research)"
	
	if mea_os == 'win32' :
		text += "\n-adir   : Sets UEFIFind to the previous directory\n"
		text += "-ubu    : SoniX/LS_29's UEFI BIOS Updater mode\n"
		text += "-ubupre : SoniX/LS_29's UEFI BIOS Updater Pre-Menu mode\n"
		text += "-extr   : Lordkag's UEFIStrip mode\n"
		text += "-msg    : Prints only messages without headers\n"
		text += "-hid    : Displays all firmware even without messages (-msg)\n"
		text += "-aecho  : Alternative display of empty lines (-msg, -hid)"
	
	print(text)
	mea_exit(0)

# https://stackoverflow.com/a/22881871
def get_script_dir(follow_symlinks=True) :
	if getattr(sys, 'frozen', False) :
		path = os.path.abspath(sys.executable)
	else :
		path = inspect.getabsfile(get_script_dir)
	if follow_symlinks :
		path = os.path.realpath(path)

	return os.path.dirname(path)

# https://stackoverflow.com/a/781074
def show_exception_and_exit(exc_type, exc_value, tb) :
	print(col_r + '\nError: MEA just crashed, please report the following:\n')
	traceback.print_exception(exc_type, exc_value, tb)
	input(col_e + "\nPress enter to exit")
	colorama.deinit() # Stop Colorama
	sys.exit(-1)

def mea_exit(code=0) :
	colorama.deinit() # Stop Colorama
	if param.ubu_mea_pre or param.ubu_mea or param.extr_mea or param.print_msg : sys.exit(code)
	input("\nPress enter to exit")
	sys.exit(code)

# Calculate SHA1 hash of data
def sha_1(data) :
	return hashlib.sha1(data).hexdigest()
	
# Calculate SHA256 hash of data
def sha_256(data) :
	return hashlib.sha256(data).hexdigest()

# Must be called at the end of analysis to gather all available messages, if any
def multi_drop() :
	if err_stor or warn_stor or note_stor : # Any note, warning or error copies the file
		f.close()
		suffix = 0
		
		file_name = os.path.basename(file_in)
		check_dir = mea_dir + os_dir + '__CHECK__' + os_dir
		
		if not os.path.isdir(check_dir) : os.mkdir(check_dir)
		
		while os.path.exists(check_dir + file_name) :
			suffix += 1
			file_name += '_%s' % suffix
		
		shutil.copyfile(file_in, check_dir + file_name)

def db_open() :
	fw_db = open(db_path, "r")
	return fw_db
	
def check_upd(key) :
	upd_key_found = False
	vlp = [0]*4
	fw_db = db_open()
	for line in fw_db :
		if len(line) < 2 or line[:3] == "***" :
			continue # Skip empty lines or comments
		elif key in line :
			upd_key_found = True
			wlp = line.strip().split('__') # whole line parts
			vlp = wlp[1].strip().split('.') # version line parts
			for i in range(len(vlp)) : vlp[i] = int(vlp[i])
			break
	fw_db.close()
	if upd_key_found : return vlp[0],vlp[1],vlp[2],vlp[3]
	else : return 0,0,0,0

# Split & space bytes at every 2 characters
def str_split_as_bytes(input_bytes) :
	return ' '.join([input_bytes[i:i + 2] for i in range(0, len(input_bytes), 2)])

# General MEA Messages
def gen_msg(msg_type,msg,command) :
	if command == 'del' : del err_stor[:]
	
	if not param.print_msg: print('\n' + msg)
				
	if (not err_stor) and (not warn_stor) and (not note_stor): msg_type.append(msg)
	else: msg_type.append('\n' + msg)

# Detect SPI with Intel Flash Descriptor
def spi_fd_init() :
	fd_match = (re.compile(br'\xFF\xFF\xFF\xFF\x5A\xA5\xF0\x0F')).search(reading) # 16xFF + Z¥π. detection (PCH)
	if fd_match is None :
		fd_match = (re.compile(br'\x5A\xA5\xF0\x0F.{172}\xFF{16}', re.DOTALL)).search(reading) # Z¥π. + [0xAC] + 16xFF fallback (ICH)
		start_substruct = 0x0
		end_substruct = 0xBC - 0x10 # 0xBC for [0xAC] + 16xFF sanity check, 0x10 extra before ICH FD Regions
	else :
		start_substruct = 0xC
		end_substruct = 0x0

	if fd_match is not None :
		(start_fd_match, end_fd_match) = fd_match.span()
		return True, start_fd_match - start_substruct, end_fd_match - end_substruct
	else :
		return False, 0, 0

# Analyze Intel FD after Reading, Major, Variant
def spi_fd(action,start_fd_match,end_fd_match) :
	if action == 'unlocked' :
		# 0xh FF FF = 0b 1111 1111 1111 1111 --> All 8 (0-7) regions Read/Write unlocked by CPU/BIOS
		if (variant == 'ME' and major <= 10) or (variant == 'TXE' and major <= 2) : # CPU/BIOS, ME, GBE check
			fd_bytes = reading[end_fd_match + 0x4E:end_fd_match + 0x50] + reading[end_fd_match + 0x52:end_fd_match + 0x54] \
					   + reading[end_fd_match + 0x56:end_fd_match + 0x58]
			fd_bytes = binascii.b2a_hex(fd_bytes).decode('utf-8').upper()
			if fd_bytes == 'FFFFFFFFFFFF' : return 2 # Unlocked FD
			else : return 1 # Locked FD
		elif variant == 'ME' and major > 10 : # CPU/BIOS, ME, GBE, EC check
			fd_bytes = reading[end_fd_match + 0x6D:end_fd_match + 0x70] + reading[end_fd_match + 0x71:end_fd_match + 0x74] \
					   + reading[end_fd_match + 0x75:end_fd_match + 0x78] + reading[end_fd_match + 0x7D:end_fd_match + 0x80]
			fd_bytes = binascii.b2a_hex(fd_bytes).decode('utf-8').upper()
			if fd_bytes == 'FFFFFFFFFFFFFFFFFFFFFFFF' : return 2 # Unlocked FD
			else : return 1 # Locked FD
		elif variant == 'TXE' and major > 2 :
			fd_bytes = reading[end_fd_match + 0x6D:end_fd_match + 0x70] + reading[end_fd_match + 0x71:end_fd_match + 0x74]
			fd_bytes = binascii.b2a_hex(fd_bytes).decode('utf-8').upper()
			if fd_bytes == 'FFFFFFFFFFFF' : return 2 # Unlocked FD
			else : return 1 # Locked FD
	elif action == 'region' :
		me_fd_base = int.from_bytes(reading[end_fd_match + 0x34:end_fd_match + 0x36], 'little')
		me_fd_limit = int.from_bytes(reading[end_fd_match + 0x36:end_fd_match + 0x38], 'little')
		if me_fd_limit != 0 :
			me_fd_start = me_fd_base * 0x1000 + start_fd_match # fd_match required in case FD is not at the start of image
			me_fd_size = (me_fd_limit + 1 - me_fd_base) * 0x1000 # The +1 is required to include last Region byte
			return True,me_fd_start,me_fd_size # FD found, ME Region exists
		else :
			return False,0,0 # FD found, ME Region missing
		
def fw_ver(major,minor,hotfix,build) :
	if variant == "SPS" :
		if sub_sku != "NaN" : version = "%s.%s.%s.%s.%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), sub_sku) # xx.xx.xx.xxx.y
		else : version = "%s.%s.%s.%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build)) # xx.xx.xx.xxx
	else :
		version = "%s.%s.%s.%s" % (major, minor, hotfix, build)
	
	return version
	
def fuj_umem_ver(me_fd_start) :
	rgn_fuj_hdr = reading[me_fd_start:me_fd_start + 0x4]
	rgn_fuj_hdr = binascii.b2a_hex(rgn_fuj_hdr).decode('utf-8').upper()
	version = "NaN"
	if rgn_fuj_hdr == "554DC94D" : # Futjitsu Compressed ME Region with header UMEM
		major = int(binascii.b2a_hex(reading[me_fd_start + 0xB:me_fd_start + 0xD][::-1]), 16)
		minor = int(binascii.b2a_hex(reading[me_fd_start + 0xD:me_fd_start + 0xF][::-1]), 16)
		hotfix = int(binascii.b2a_hex(reading[me_fd_start + 0xF:me_fd_start + 0x11][::-1]), 16)
		build = int(binascii.b2a_hex(reading[me_fd_start + 0x11:me_fd_start + 0x13][::-1]), 16)
		version = "%s.%s.%s.%s" % (major, minor, hotfix, build)
	
	return version

# Taken directly from Lordkag's UEFI Strip!
def switch_guid (guid, transform) :
	vol = ''

	if transform == "GUID2HEX" :
		vol = guid[6:8] + guid[4:6] + guid[2:4] + guid[:2] + guid[11:13] + guid[9:11] + guid[16:18]
		vol += guid[14:16] + guid[19:23] + guid[24:]
	elif transform == "HEX2GUID" :
		vol = guid[6:8] + guid[4:6] + guid[2:4] + guid[:2] + "-" + guid[10:12] + guid[8:10] + "-"
		vol += guid[14:16] + guid[12:14] + "-" + guid[16:20] + "-" + guid[20:]
	
	return vol.upper()
	
# Check if Fixed Offset Variables (FOVD/NVKR) section is dirty
def fovd_clean (fovdtype) :
	fovd_match = None
	fovd_data = b''
	
	if fovdtype == "new" : fovd_match = (re.compile(br'\x46\x4F\x56\x44\x4B\x52\x49\x44')).search(reading) # FOVDKRID detection
	elif fovdtype == "old" : fovd_match = (re.compile(br'\x4E\x56\x4B\x52\x4B\x52\x49\x44')).search(reading) # NVKRKRID detection
	
	if fovd_match is not None :
		(start_fovd_match, end_fovd_match) = fovd_match.span()
		fovd_start = int.from_bytes(reading[end_fovd_match:end_fovd_match + 0x4], 'little')
		fovd_size = int.from_bytes(reading[end_fovd_match + 0x4:end_fovd_match + 0x8], 'little')
		if fovdtype == "new" : fovd_data = reading[fpt_start + fovd_start:fpt_start + fovd_start + fovd_size]
		elif fovdtype == "old" :
			fovd_size = int.from_bytes(reading[fovd_start + 0x19:fovd_start + 0x1C], 'little')
			fovd_data = reading[fpt_start + fovd_start + 0x1C:fpt_start + fovd_start + 0x1C + fovd_size]
		if fovd_data == b'\xFF' * fovd_size : return True
		else : return False
	else : return True

# Create Firmware Type Database Entry
def fw_types(fw_type) :
	type_db = 'NaN'
	
	if variant == "SPS" and (fw_type == "Region" or fw_type == "Region, Stock" or fw_type == "Region, Extracted") : # SPS --> Region (EXTR at DB)
		fw_type = "Region"
		type_db = "EXTR"
	elif fw_type == "Region, Extracted" : type_db = "EXTR"
	elif fw_type == "Region, Stock" or fw_type == "Region" : type_db = "RGN"
	elif fw_type == "Update" : type_db = "UPD"
	elif fw_type == "Operational" : type_db = "OPR"
	elif fw_type == "Recovery" : type_db = "REC"
	elif fw_type == "Unknown" : type_db = "UNK"
	
	return fw_type, type_db
	
# Validate Manifest RSA Signature
def rsa_sig_val(man_hdr_struct, check_start) :
	man_hdr = man_hdr_struct.HeaderLength * 4
	man_size = man_hdr_struct.Size * 4
	man_pexp = man_hdr_struct.RsaPubExp
	man_pkey = int((''.join('%0.8X' % int.from_bytes(struct.pack('<I', val), 'little') for val in reversed(man_hdr_struct.RsaPubKey))), 16)
	man_sign = int((''.join('%0.8X' % int.from_bytes(struct.pack('<I', val), 'little') for val in reversed(man_hdr_struct.RsaSig))), 16)
	
	dec_sign = '%X' % pow(man_sign, man_pexp, man_pkey) # Decrypted Signature
	
	if (variant == 'ME' and major < 6) or (variant == 'SPS' and major < 2) : # SHA-1
		rsa_hash = hashlib.sha1()
		dec_hash = dec_sign[-40:] # 160-bit
	else : # SHA-256
		rsa_hash = hashlib.sha256()
		dec_hash = dec_sign[-64:] # 256-bit
	
	rsa_hash.update(reading[check_start:check_start + 0x80]) # First 0x80 before RSA area
	rsa_hash.update(reading[check_start + man_hdr:check_start + man_size]) # Manifest protected data
	rsa_hash = rsa_hash.hexdigest().upper() # Data SHA-1 or SHA-256 Hash
	
	return [dec_hash == rsa_hash, dec_hash, rsa_hash]
	
# Unpack Engine x86 firmware
def x86_unpack(fpt_part_all, fw_type) :
	part_details = []
	cpd_match_ranges = []
	
	# Get Firmware Type DB
	fw_type, type_db = fw_types(fw_type)
	
	# Create firmware extraction folder
	if variant == 'SPS' : fw_name = "%s.%s.%s.%s_%s_%s" % (major, minor, hotfix, build, rel_db, type_db) # No SKU SPS4
	else : fw_name = "%s.%s.%s.%s_%s_%s_%s" % (major, minor, hotfix, build, sku_db, rel_db, type_db)
	if os.path.isdir(mea_dir + os_dir + fw_name) : shutil.rmtree(mea_dir + os_dir + fw_name)
	os.mkdir(fw_name)
	
	# Parse all Flash Partition Table entries
	if len(fpt_part_all) :
		for part in fpt_part_all :
			# Store Partition details
			part_details.append(('\t%4s     0x%.6X     0x%.6X     %4s' % (part[0].decode('utf-8'),part[1],part[2],part[3])))
		
		print(col_y + '\n\tDetected %s Partition(s):\n\n\tName      Start         End         ID\n' % len(fpt_part_all) + col_e)
		for detail in part_details : print(detail)
		
		# Charted Partitions include fpt_start, Uncharted not (RGN only, non-SPI)
		for part in fpt_part_all :
			part_name = part[0].decode('utf-8')
			part_start = part[1]
			part_end = part[2]
			part_inid = part[3]
			
			if part_inid != '----' : part_name += '_%s' % part_inid
			
			file_name = fw_name + os_dir + part_name + '.bin'
			
			part_data = reading[part_start:part_end]
			with open(file_name, 'w+b') as part_file : part_file.write(part_data)
	
	# Code Partition Directory detection
	cpd_pat = re.compile(br'\x24\x43\x50\x44.\x00\x00\x00\x01\x01\x10', re.DOTALL) # $CPD detection
	cpd_match_store = list(cpd_pat.finditer(reading))
	
	# Store all Code Partition Directory ranges
	if len(cpd_match_store) :
		for cpd in cpd_match_store : cpd_match_ranges.append(cpd)
	
	# Parse all Code Partition Directory entries
	for cpdrange in cpd_match_ranges :
		(start_cpd_emod, end_cpd_emod) = cpdrange.span()
						
		cpd_offset_e,cpd_mod_attr_e,cpd_ext_attr_e,un1,un2,un3,un4 = ext_anl('$CPD', start_cpd_emod)
						
		mod_anl('extr', cpd_offset_e, cpd_mod_attr_e, cpd_ext_attr_e, fw_name)
	
# Analyze Engine x86 $CPD Offset & Extensions
# noinspection PyUnusedLocal
def ext_anl(input_type, input_offset) :
	vcn = -1
	in_id = -1
	cpd_num = -1
	ext_empty = 0
	fw_0C_lbg = -1
	fw_0C_sku1 = -1
	fw_0C_sku2 = -1
	cpd_offset = -1
	start_man_match = -1
	cpd_ext_offset = 0
	mod_empty = 0
	cpd_mod_attr = []
	cpd_ext_attr = []
	cpd_ext_names = []
	mn2_sigs = [False, -1, -1]
	ext_tag_all = list(range(22)) # $CPD Extensions 0x00-0x15
	
	if input_type == '$MN2' :
		start_man_match = input_offset
		
		# Scan backwards for $CPD (should be <= 0x500B, works with both RGN --> $FPT & UPD --> 0x0)
		for offset in range(start_man_match + 2, start_man_match - 0x1000, -4): # Start from MN2 (no $) to catch $CPD at 1, before "for" break at 0
			if b'$CPD' in reading[offset - 1:offset - 1 + 4] :
				cpd_offset = offset - 1 # Catch UPD $CPD at offset 0 (offset - 1 = 1 - 1 = 0)
				break # Stop at first detected $CPD
	elif input_type == '$CPD' :
		cpd_offset = input_offset
		
		# Scan forward for $MN2 (should be <= 0x500B)
		mn2_pat = re.compile(br'\x00\x24\x4D\x4E\x32').search(reading[cpd_offset:cpd_offset + 0x1000]) # .$MN2 detection, 0x00 adds old ME RGN support
		if mn2_pat is not None :
			(start_man_match, end_man_match) = mn2_pat.span()
			start_man_match += cpd_offset
			end_man_match += cpd_offset
	
	# $MN2 existence not mandatory
	if start_man_match != -1 :
		mn2_hdr = get_struct(reading, start_man_match - 0x1B, MN2_Manifest)
		if param.me11_mod_extr : mn2_sigs = rsa_sig_val(mn2_hdr, start_man_match - 0x1B) # For each Partition
	
	# $CPD detected
	if cpd_offset > -1 :
		cpd_hdr = get_struct(reading, cpd_offset, CPD_Header)
		cpd_num = cpd_hdr.NumModules
		cpd_name = cpd_hdr.PartitionName.decode('utf-8')
			
		# Analyze Manifest & Metadata (must be before Module analysis)
		for entry in range(0, cpd_num) :
			cpd_entry_hdr = get_struct(reading, cpd_offset + 0x10 + entry * 0x18, CPD_Entry)
			cpd_off_attr = format(cpd_entry_hdr.OffsetAttrib, '032b') # 32 bits (LE)
			cpd_mod_off = int(cpd_off_attr[7:], 2) # $CPD Entry Offset Attribute Address (from $CPD, 25 bits)
			cpd_mod_comp = int(cpd_off_attr[6], 2) # $CPD Entry Offset Attribute Compressed (0 No, 1 Yes)
			cpd_mod_res = int(cpd_off_attr[:6], 2) # $CPD Entry Offset Attribute Reserved (0, 6 bits)
			cpd_entry_offset = cpd_offset + cpd_mod_off
			cpd_entry_size = cpd_entry_hdr.Size # Uncompressed only
			cpd_entry_name = cpd_entry_hdr.Name
			
			if b'.man' in cpd_entry_name or b'.met' in cpd_entry_name :
				
				# Set initial $CPD Extension Offset
				if b'.man' in cpd_entry_name : cpd_ext_offset = cpd_entry_offset + mn2_hdr.HeaderLength * 4 # Skip $MN2 at .man
				elif b'.met' in cpd_entry_name : cpd_ext_offset = cpd_entry_offset # Metadata is always Uncompressed
				
				# Analyze all Manifest & Metadata Extensions
				ext_tag = int.from_bytes(reading[cpd_ext_offset:cpd_ext_offset + 0x4], 'little') # Initial Extension Tag
				
				while ext_tag in ext_tag_all :
							
					if ext_tag == 3 : # Unique, .man (ME)
						ext_hdr = get_struct(reading, cpd_ext_offset, CPD_Ext_03)
						vcn = ext_hdr.VCN
						in_id = ext_hdr.InstanceID # LOCL/WCOD identifier
					elif ext_tag == 10 : # Unique, .met
						ext_hdr = get_struct(reading, cpd_ext_offset, CPD_Ext_0A)
						mod_comp_type = ext_hdr.Compression # Metadata's Module Compression Type (0-2)
						mod_encr_type = ext_hdr.Encryption # Metadata's Module Encryption Type (0-1)
						mod_comp_size = ext_hdr.SizeComp # Metadata's Module Compressed Size ($CPD Entry's Module Size is always Uncompressed)
						mod_uncomp_size = ext_hdr.SizeUncomp # Metadata's Module Uncompressed Size (equal to $CPD Entry's Module Size)
						mod_hash = ''.join('%0.8X' % int.from_bytes(struct.pack('<I', val), 'little') for val in reversed(ext_hdr.Hash)) # Metadata's Module Hash
						cpd_mod_attr.append([cpd_entry_name.decode('utf-8')[:-4], mod_comp_type, mod_encr_type, 0, mod_comp_size, mod_uncomp_size, 0, mod_hash, cpd_name, 0, mn2_sigs])
					elif ext_tag == 15 : # Unique, .man (TXE)
						ext_hdr = get_struct(reading, cpd_ext_offset, CPD_Ext_0F)
						vcn = ext_hdr.VCN
					elif ext_tag == 12 : # Unique, .man
						ext_hdr = get_struct(reading, cpd_ext_offset, CPD_Ext_0C)
						fw_sku_attr = format(ext_hdr.FWSKUAttrib, '032b') # 32 bits (LE)
						fw_0C_cse = int(fw_sku_attr[28:32], 2) # CSE Size * 0.5MB (0)
						fw_0C_sku1 = int(fw_sku_attr[25:28], 2) # SKU Type (0 COR, 1 CON, 2 SLM)
						fw_0C_lbg = int(fw_sku_attr[24], 2) # Lewisburg support (0 11.x, 1 11.20)
						fw_0C_m3 = int(fw_sku_attr[23], 2) # M3 support (0 CON & SLM, 1 COR)
						fw_0C_m0 = int(fw_sku_attr[22], 2) # M0 support (1 CON & SLM & COR)
						fw_0C_sku2 = int(fw_sku_attr[20:22], 2) # Unknown/SKU Platform (0 for H/LP <= 11.0.0.1202, 0 for H >= 11.0.0.1205, 1 for LP >= 11.0.0.1205)
						fw_0C_sicl = int(fw_sku_attr[16:20], 2) # Si Class H M L (2 CON & SLM, 4 COR)
						fw_0C_res2 = int(fw_sku_attr[:16], 2) # Reserved (0)
					
					cpd_ext_offset += int.from_bytes(reading[cpd_ext_offset + 0x4:cpd_ext_offset + 0x8], 'little')
					if cpd_ext_offset + 1 > cpd_entry_offset + cpd_entry_hdr.Size : # End of Extension reached
						
						ext_data = reading[cpd_entry_offset:cpd_entry_offset + cpd_entry_size]
						if ext_data == b'\xFF' * cpd_entry_size : ext_empty = 1 # Determine if Extension is Empty/Missing
						cpd_ext_attr.append([cpd_entry_name.decode('utf-8'), cpd_mod_comp, 0, cpd_entry_offset, cpd_entry_size, cpd_entry_size, ext_empty, 0, cpd_name, in_id, mn2_sigs])
						cpd_ext_names.append(cpd_entry_name.decode('utf-8')[:-4]) # Store Module names which have Metadata
							
						break # Stop Extension scanning at the end of .man/.met
					ext_tag = int.from_bytes(reading[cpd_ext_offset:cpd_ext_offset + 0x4], 'little') # Next Extension Tag
		
		# Analyze Modules, Keys & Data (must be after Manifest & Metadata Extension analysis)
		for entry in range(0, cpd_num) :
			cpd_entry_hdr = get_struct(reading, cpd_offset + 0x10 + entry * 0x18, CPD_Entry)
			cpd_off_attr = format(cpd_entry_hdr.OffsetAttrib, '032b') # 32 bits (LE)
			cpd_mod_off = int(cpd_off_attr[7:], 2) # $CPD Entry Offset Attribute Address (from $CPD, 25 bits)
			cpd_entry_name = cpd_entry_hdr.Name
			cpd_entry_size = cpd_entry_hdr.Size # Uncompressed only
			cpd_entry_offset = cpd_offset + cpd_mod_off
			
			# Manifest & Metadata Skip
			if b'.man' in cpd_entry_name or b'.met' in cpd_entry_name : continue
			
			# Modules with Metadata
			elif cpd_entry_name.decode('utf-8') in cpd_ext_names :
			
				# Set Module's starting offset at Module Attributes list
				for mod in range(len(cpd_mod_attr)) :
					if cpd_mod_attr[mod][0] == cpd_entry_name.decode('utf-8') :
						
						cpd_mod_attr[mod][3] = cpd_entry_offset # Fill Module Starting Offset from $CPD Entry
						cpd_mod_attr[mod][9] = in_id # Fill Module Instance ID from CPD_Ext_03
						
						mod_comp_size = cpd_mod_attr[mod][4] # Store Module Compressed Size for Empty check
						mod_data = reading[cpd_entry_offset:cpd_entry_offset + mod_comp_size] # Store Module data for Empty check
						if mod_data == b'\xFF' * mod_comp_size : cpd_mod_attr[mod][6] = 1 # Determine if Module is Empty/Missing
						
						break
			
			# Keys
			elif '.key' in cpd_entry_name.decode('utf-8') :
				mod_data = reading[cpd_entry_offset:cpd_entry_offset + cpd_entry_size]
				if mod_data == b'\xFF' * cpd_entry_size : mod_empty = 1 # Determine if Key is Empty/Missing
				
				# Validate Key's RSA Signature
				mn2_key_hdr = get_struct(reading, cpd_entry_offset, MN2_Manifest)
				mn2_key_sigs = rsa_sig_val(mn2_key_hdr, cpd_entry_offset)
					
				cpd_mod_attr.append([cpd_entry_name.decode('utf-8'), 0, 0, cpd_entry_offset, cpd_entry_size, cpd_entry_size, mod_empty, 0, cpd_name, 0, mn2_key_sigs])
			
			# Generic Data
			else :
				mod_data = reading[cpd_entry_offset:cpd_entry_offset + cpd_entry_size]
				if mod_data == b'\xFF' * cpd_entry_size : mod_empty = 1 # Determine if Module is Empty/Missing
				
				cpd_mod_attr.append([cpd_entry_name.decode('utf-8'), 0, 0, cpd_entry_offset, cpd_entry_size, cpd_entry_size, mod_empty, 0, cpd_name, 0, mn2_sigs])

	#for test in cpd_mod_attr : print(test)
	
	return cpd_offset, cpd_mod_attr, cpd_ext_attr, vcn, fw_0C_sku1, fw_0C_lbg, fw_0C_sku2

# Analyze & Store Engine x86 Modules
def mod_anl(action, cpd_offset, cpd_mod_attr, cpd_ext_attr, fw_name) :
	ker_start = -1
	ker_end = -1
	mea_hash_u = 0
	mea_hash_c = 0
	comp = ['Uncompressed','Huffman','LZMA']
	fext = ['mod','huff','lzma']
	encr_empty = ['No','Yes']
	mod_names = []
	mod_details = []
	
	# $CPD validity verified
	if cpd_offset > -1 :
		
		cpd_all_attr = cpd_ext_attr + cpd_mod_attr
		
		for mod in cpd_all_attr :
			mod_names.append(mod[0]) # Store Module names
			mod_details.append(('\t%12s \t%8s\t%4s\t    0x%.6X\t 0x%.6X      0x%.6X\t  %4s' %
								(mod[0],comp[mod[1]],encr_empty[mod[2]],mod[3],mod[4],mod[5],encr_empty[mod[6]]))) # Store Module details
			
			# Store Kernel Start & End for SKU analysis
			if mod[0] == 'kernel' :
				ker_start = mod[3]
				ker_end = ker_start + mod[4]
		
		if action == 'extr' :
			
			# Parent Partition Attributes (same for all cpd_all_attr list instance entries)
			cpd_pname = cpd_all_attr[0][8] # $CPD PartitionName
			ext_inid = cpd_all_attr[0][9] # Partition Instance ID
			mn2_valid = cpd_all_attr[0][10][0] # Partition Signature Validation
			# noinspection PyUnusedLocal
			mn2_sig_dec = cpd_all_attr[0][10][1] # Partition Signature Decrypted
			# noinspection PyUnusedLocal
			mn2_sig_sha = cpd_all_attr[0][10][2] # Partition Signature Data Hash
			
			if cpd_pname in ['LOCL','WCOD'] :
				print(col_y + '\n\tDetected %s Module(s) at %s %0.4X:\n\n\t      Module\tCompression   Encryption    Offset\t SizeComp    SizeUncomp   Empty\n' % \
						(len(cpd_all_attr), cpd_pname, ext_inid) + col_e)
			else :
				print(col_y + '\n\tDetected %s Module(s) at %s:\n\n\t      Module\tCompression   Encryption    Offset\t SizeComp    SizeUncomp   Empty\n' % \
						(len(cpd_all_attr), cpd_pname) + col_e)
			
			for detail in mod_details : print(detail)
			
			#in_mod_name = input('\nEnter module name or * for all: ') # Asks at all Partitions, better use * for all
			in_mod_name = '*'
			
			if in_mod_name not in mod_names and in_mod_name != '*' :
				print(col_r + '\n\tError: Could not find module "%s"' % in_mod_name + col_e)
				
				return ker_start, ker_end # Invalid input, return function-essential Kernel info
			
			if cpd_pname not in ['LOCL','WCOD'] : folder_name = mea_dir + os_dir + fw_name + os_dir + cpd_pname + os_dir
			else : folder_name = mea_dir + os_dir + fw_name + os_dir + '%s_%0.4X' % (cpd_pname, ext_inid) + os_dir
			os.mkdir(folder_name)
			
			# Parse all Modules based on their Metadata
			for mod in cpd_all_attr :
				mod_name = mod[0] # Name
				mod_comp = mod[1] # Compression
				mod_encr = mod[2] # Encryption
				mod_start = mod[3] # Starting Offset
				mod_size_comp = mod[4] # Compressed Size
				mod_size_uncomp = mod[5] # Uncompressed Size
				mod_empty = mod[6] # Empty/Missing
				mod_hash = mod[7] # Hash (LZMA --> Compressed + zeroes, Huffman --> Uncompressed)
				mod_end = mod_start + mod_size_comp # Ending Offset
				
				if in_mod_name != '*' and in_mod_name != mod_name : continue # Wait for requested Module only
				
				if mod_empty == 1 : continue # Skip Empty/Missing Modules
				
				if '.man' in mod_name or '.met' in mod_name :
					mod_fname = folder_name + mod_name
					mod_type = 'metadata'
				else :
					mod_fname = folder_name + '%s.%s' % (mod_name, fext[mod_comp])
					mod_type = 'module'
					
				mod_data = reading[mod_start:mod_end]

				# Initialization for Module Storing
				if mod_comp == 2 :
					# Calculate LZMA Module SHA256 hash
					mea_hash_c = sha_256(mod_data).upper() # Compressed, Header zeroes included (most LZMA Modules)
					
					# Remove zeroes from LZMA header for decompression (inspired from Igor Skochinsky's me_unpack)
					if mod_data.startswith(b'\x36\x00\x40\x00\x00') and mod_data[0xE:0x11] == b'\x00\x00\x00' :
						mod_data = mod_data[:0xE] + mod_data[0x11:] # Visually, mod_size_comp += -3 for compressed module
				
				# Store Metadata or Module for further actions
				with open(mod_fname, 'w+b') as mod_file : mod_file.write(mod_data)
				
				# Extract & Ignore Encrypted Modules
				if mod_encr == 1 :
					print(col_y + '\n\t--> Stored Encrypted %s "%s" [0x%.5X - 0x%.5X]' % (mod_type, mod_name, mod_start, mod_end - 0x1) + col_e)
					
					#print('\n\t    MOD: %s' % mod_hash) # Debug
					
					print(col_m + '\n\t    Hash of %s %s "%s" is UNKNOWN' % (comp[mod_comp], mod_type, mod_name) + col_e)
					
					os.rename(mod_fname, mod_fname[:-5] + '.encr') # Change file extension from .lzma to .encr
					
					#if mod_name != 'pavp' : input() # Debug
					
					continue # Module Encryption on top of Compression, skip decompression
				else :
					print(col_y + '\n\t--> Stored %s %s "%s" [0x%.5X - 0x%.5X]' % (comp[mod_comp], mod_type, mod_name, mod_start, mod_end - 0x1) + col_e)
				
				# Extract & Validate Uncompressed Data
				if mod_comp == 0 :
					# Manifest & Metadata
					if '.man' in mod_name or '.met' in mod_name :
						#print('\n\t    MN2: %s' % mn2_sig_dec) # Debug
						#print('\t    MEA: %s' % mn2_sig_sha) # Debug
					
						if mn2_valid : print(col_g + '\n\t    RSA Signature of partition "%s" is VALID' % cpd_pname + col_e)
						else :
							print(col_r + '\n\t    RSA Signature of partition "%s" is INVALID' % cpd_pname + col_e)
							#input() # Debug
					# Keys
					elif '.key' in mod_name :
						#print('\n\t    MN2: %s' % mn2_sig_dec) # Debug
						#print('\t    MEA: %s' % mn2_sig_sha) # Debug
					
						if mn2_valid : print(col_g + '\n\t    RSA Signature of key "%s" is VALID' % mod_name + col_e)
						else :
							print(col_r + '\n\t    RSA Signature of key "%s" is INVALID' % mod_name + col_e)
							#input() # Debug
							
						os.rename(mod_fname, mod_fname[:-4]) # Change file extension from .mod to .key
					# Data
					elif mod_hash == 0 :
						print(col_m + '\n\t    Hash of %s %s "%s" is UNKNOWN' % (comp[mod_comp], mod_type, mod_name) + col_e)
						
						os.rename(mod_fname, mod_fname[:-4]) # Change file extension from .mod to default
					# Modules
					else :
						mea_hash = sha_256(mod_data).upper()
					
						#print('\n\t    MOD: %s' % mod_hash) # Debug
						#print('\t    MEA: %s' % mea_hash) # Debug
					
						if mod_hash == mea_hash : print(col_g + '\n\t    Hash of %s %s "%s" is VALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
						else :
							print(col_r + '\n\t    Hash of %s %s "%s" is INVALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
							#input() # Debug
					
				# Extract & Decompress LZMA Modules
				if mod_comp == 2 :
					try :
						# Decompress LZMA Module via Python
						# noinspection PyArgumentList
						mod_data = lzma.LZMADecompressor().decompress(mod_data)
						
						# Add missing EOF Padding when needed (usually at NFTP.ptt Module)
						data_size_uncomp = len(mod_data)
						if data_size_uncomp != mod_size_uncomp : mod_data += b'\xFF' * (mod_size_uncomp - data_size_uncomp) 
						
						mod_fname = mod_fname[:-5] + '.mod'
						with open(mod_fname, 'w+b') as mod_file : mod_file.write(mod_data)
						print(col_c + '\n\t    Decompressed %s %s "%s" via Python' % (comp[mod_comp], mod_type, mod_name) + col_e)
						
						mea_hash_u = sha_256(mod_data).upper() # Uncompressed (few LZMA Modules)
					except :
						print(col_r + '\n\t    Failed to decompress %s %s "%s" via Python' % (comp[mod_comp], mod_type, mod_name) + col_e)
						#input() # Debug
					
					#print('\n\t    MOD  : %s' % mod_hash) # Debug
					#print('\t    MEA C: %s' % mea_hash_c) # Debug
					#print('\t    MEA U: %s' % mea_hash_u) # Debug
					
					if mod_hash == mea_hash_c or mod_hash == mea_hash_u : print(col_g + '\n\t    Hash of %s %s "%s" is VALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
					else :
						print(col_r + '\n\t    Hash of %s %s "%s" is INVALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
						#input() # Debug
				
				# Extract & Decompress or Separate Huffman Modules
				if mod_comp == 1 :
					# Decompress Huffman Module via Huffman11 by IllegalArgument (https://github.com/IllegalArgument/Huffman11)
					# Download Huffman11.py and place it at MEA dir
					
					try :
						sys.dont_write_bytecode = True
						import Huffman11
					
						mod_dname = mod_fname[:-5] + '.mod'
					
						# noinspection PyUnusedLocal
						with open(mod_fname, 'r+b') as mod_cfile :
							#mod_ddata = Huffman11.huffman_decompress(mod_cfile.read(), mod_size_comp, mod_size_uncomp) # Debug
						
							with open(os.devnull, 'w') as devnull:
								with contextlib.redirect_stdout(devnull): # Hide output
									mod_ddata = Huffman11.huffman_decompress(mod_cfile.read(), mod_size_comp, mod_size_uncomp)
						
							with open(mod_dname, 'w+b') as mod_dfile : mod_dfile.write(mod_ddata)
							
						if os.path.isfile(mod_dname) :
							print(col_c + '\n\t    Decompressed %s %s "%s" via Huffman11 by IllegalArgument' % (comp[mod_comp], mod_type, mod_name) + col_e)
									
							# Open decompressed Huffman module for hash validation
							with open(mod_dname, 'r+b') as mod_dfile :
								mea_hash = sha_256(mod_dfile.read()).upper()
										
								#print('\n\t    MOD: %s' % mod_hash) # Debug
								#print('\t    MEA: %s' % mea_hash) # Debug
										
								if mod_hash == mea_hash : print(col_g + '\n\t    Hash of %s %s "%s" is VALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
								else :
									print(col_r + '\n\t    Hash of %s %s "%s" is INVALID' % (comp[mod_comp], mod_type, mod_name) + col_e)
									#input() # Debug
						else :
							raise Exception('Decompressed file not found!')
					except ModuleNotFoundError :
						print(col_r + '\n\t    Huffman11 by IllegalArgument not found! Place Huffman11.py at MEA folder' + col_e)
						print(col_r + '\n\t    Failed to decompress %s %s "%s" via Huffman11 by IllegalArgument' % (comp[mod_comp], mod_type, mod_name) + col_e)
						#input() # Debug
					except :
						print(col_r + '\n\t    Failed to decompress %s %s "%s" via Huffman11 by IllegalArgument' % (comp[mod_comp], mod_type, mod_name) + col_e)
						#input() # Debug
					
				if in_mod_name == mod_name : break # Store only requested Module
				elif in_mod_name == '*' : pass # Store all Modules
		
	return ker_start, ker_end
		
def krod_anl() :
	me11_sku_match = (re.compile(br'\x4B\x52\x4F\x44')).finditer(reading) # KROD detection

	sku_check = "NaN"
	me11_sku_ranges = []
	
	if me11_sku_match is not None and fw_type != "Update" :
		for m in me11_sku_match : me11_sku_ranges.append(m.span()) # Find and store all KROD starting offsets and spans (SKU history)
		
		if me11_sku_ranges :
			(start_sku_match, end_sku_match) = me11_sku_ranges[-1] # Set last KROD starting & ending offsets
			
			# ChipsetInitBinary example: Skylake_SPT_H_ChipsetInit_Dx_V49 --> 147.49 (?)
			# PCH H Bx is signified by 128/129.xx versions (128.07, 129.24)
			# PCH H Cx is signified by 145.xx versions (145.24, 145.56, 145.62)
			# PCH H Dx is signified by 147/176.xx versions (147.41, 147.49, 147.52, 176.11 --> 11.6.0.1126 & up)
			# PCH LP Bx is signified by 128/129.xx versions (128.26, 129.03, 129.24, 129.62)
			# PCH LP Cx is signified by 130.xx versions (130.49, 130.52)
			
			sku_check = krod_fit_sku(start_sku_match)
			me11_sku_ranges.pop(len(me11_sku_ranges)-1)

	return sku_check, me11_sku_ranges

def krod_fit_sku(start_sku_match) :
	sku_check = reading[start_sku_match - 0x100 : start_sku_match]
	sku_check = binascii.b2a_hex(sku_check).decode('utf-8').upper()
	sku_check = str_split_as_bytes(sku_check)
	
	return sku_check
	
def db_skl(variant) :
	fw_db = db_open()

	db_sku_chk = "NaN"
	sku = "NaN"
	sku_stp = "NaN"
	sku_pdm = "UPDM"
	
	for line in fw_db :
		if len(line) < 2 or line[:3] == "***" :
			continue # Skip empty lines or comments
		elif rsa_hash in line :
			line_parts = line.strip().split('_')
			if variant == 'ME' :
				db_sku_chk = line_parts[2] # Store the SKU from DB for latter use
				sku = sku_init + " " + line_parts[2] # Cel 2 is SKU
				if line_parts[3] != "XX" : sku_stp = line_parts[3] # Cel 3 is PCH Stepping
				if 'YPDM' in line_parts[4] or 'NPDM' in line_parts[4] or 'UPDM' in line_parts[4] : sku_pdm = line_parts[4] # Cel 4 is PDM
			elif variant == 'TXE' :
				if line_parts[1] != "XX" : sku_stp = line_parts[1] # Cel 1 is PCH Stepping
			break # Break loop at 1st rsa_hash match
	fw_db.close()

	return db_sku_chk, sku, sku_stp, sku_pdm
	
def db_pkey() :
	fw_db = db_open()

	pkey_var = "NaN"
	
	for line in fw_db :
		if len(line) < 2 or line[:3] == "***" :
			continue # Skip empty lines or comments
		elif rsa_pkey in line :
			line_parts = line.strip().split('_')
			pkey_var = line_parts[1] # Store the Variant
			break # Break loop at 1st rsa_pkey match
	fw_db.close()

	return pkey_var

def intel_id() :
	intel_id = reading[start_man_match - 0xB:start_man_match - 0x9]
	intel_id = binascii.b2a_hex(intel_id[::-1]).decode('utf-8')
	
	# Initial Manifest is a false positive
	if intel_id != "8086" : return 'continue'
	
	return 'OK'
	
def rsa_anl() :
	rsa_sig = reading[end_man_match + 0x164:end_man_match + 0x264] # Read RSA Signature of Recovery
	rsa_hash = sha_1(rsa_sig).upper() # SHA-1 hash of RSA Signature
	
	rsa_pkey = reading[end_man_match + 0x60:end_man_match + 0x70] # Read RSA Public Key of Recovery
	rsa_pkey = binascii.b2a_hex(rsa_pkey).decode('utf-8').upper() # First 0x10 of RSA Public Key
	
	return rsa_hash, rsa_pkey
	
# Print all Errors, Warnings & Notes (must be Errors > Warnings > Notes)
# Rule 1: If -msg -hid or -msg only: none at the beginning & one empty line at the end (only when messages exist)
# Rule 2: If -msg -aecho: one empty line at the beginning & none at the end (only when messages exist)
# Note: Does not work properly with Partial Update images, ignored due to irrelevance
def msg_rep() :
	global name_db # Must be global to avoid python error
	
	if (err_stor or warn_stor or note_stor) and param.alt_msg_echo : print("") # Rule 2
	elif param.alt_msg_echo and param.hid_find : print("") # When both -hid and -aecho, aecho prefered due to Rule 2
	
	if param.hid_find : # Parameter -hid always prints a message whether the error/warning/note arrays are empty or not
		if me_rec_ffs : print(col_y + "MEA: Found Intel %s Recovery Module %s_NaN_REC in file!" % (variant, fw_ver(major,minor,hotfix,build)) + col_e)
		else : print(col_y + "MEA: Found Intel %s firmware %s in file!" % (variant, name_db) + col_e)
		
		if err_stor or warn_stor or note_stor : print("") # Separates -hid from -msg output (only when messages exist, Rule 1 compliant)
		
	for i in range(len(err_stor)) : print(err_stor[i])
	for i in range(len(warn_stor)) : print(warn_stor[i])
	for i in range(len(note_stor)) : print(note_stor[i])
	
	if (err_stor or warn_stor or note_stor) and not param.alt_msg_echo : print("") # Rule 1
	elif not param.alt_msg_echo and param.hid_find : print("") # Rule 1, -hid without any other messages

# Force string to be printed as ASCII, ignore errors
def force_ascii(string) :
	# Input string is bare and only for printing (no open(), no Colorama etc)
	ascii_str = str((string.encode('ascii', 'ignore')).decode('utf-8', 'ignore'))
	
	return ascii_str
	
def mass_scan(f_path) :
	mass_files = []
	for root, dirs, files in os.walk(f_path, topdown=False):
		for name in files :
			mass_files.append(os.path.join(root, name))
			
	input('\nFound %s file(s)\n\nPress enter to start' % len(mass_files))
	
	return mass_files
	
# Get script location
mea_dir = get_script_dir()

# Get MEA Parameters from input
param = MEA_Param(sys.argv)

# Enumerate parameter input
arg_num = len(sys.argv)

# Set dependencies paths
db_path = mea_dir + os_dir + 'MEA.dat'
if param.alt_dir :
	top_dir = os.path.dirname(mea_dir) # Get parent dir of mea_dir -> UBU folder or UEFI_Strip folder
	uf_path = top_dir + os_dir + uf_exec
else :
	uf_path = mea_dir + os_dir + uf_exec

if not param.skip_intro :
	db_rev = mea_hdr_init()
	mea_hdr(db_rev)

	print("\nWelcome to Intel Engine firmware Analysis Tool\n")
	
	if arg_num == 2 :
		print("Press Enter to skip or input -? to list options\n")
		print("\nFile:       " + col_g + "%s" % force_ascii(os.path.basename(sys.argv[1])) + col_e)
	elif arg_num > 2 :
		print("Press Enter to skip or input -? to list options\n")
		print("\nFiles:       " + col_y + "Multiple" + col_e)
	else :
		print('Input a filename or "filepath" or press Enter to list options\n')
		print("\nFile:       " + col_m + "None" + col_e)

	input_var = input('\nOption(s):  ')
	
	# Anything quoted ("") is taken as one (file paths etc)
	input_var = re.split(''' (?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', input_var.strip())
	
	# Get MEA Parameters based on given Options
	param = MEA_Param(input_var)
	
	# Non valid parameters are treated as files
	if input_var[0] != "" :
		for i in input_var:
			if i not in param.val :
				sys.argv.append(i.strip('"'))
	
	# Re-enumerate parameter input
	arg_num = len(sys.argv)
	
	os.system(cl_wipe)
	
	mea_hdr(db_rev)
	
if (arg_num < 2 and not param.help_scr and not param.mass_scan) or param.help_scr :
	mea_help()
	mea_exit(5)

# Actions for MEA but not UBU or UEFIStrip
if param.ubu_mea_pre or param.ubu_mea or param.extr_mea or param.print_msg :
	pass
else :
	sys.excepthook = show_exception_and_exit # Pause after any unexpected python exception
	if mea_os == 'win32' : ctypes.windll.kernel32.SetConsoleTitleW(title) # Set console window title

if param.mass_scan :
	in_path = input('\nType the full folder path : ')
	source = mass_scan(in_path)
else :
	source = sys.argv[1:] # Skip script/executable

# Check if dependencies exist
depend_db = os.path.isfile(db_path)
depend_uf = os.path.isfile(uf_path)

# Connect to DB, if it exists
if depend_db :
	pass
else :
	print(col_r + "\nError: MEA.dat file is missing!" + col_e)
	mea_exit(1)

if param.enable_uf and not depend_uf :
	if not param.print_msg : print(col_r + "\nError: UEFIFind file is missing!" + col_e)
	mea_exit(1)
	
for file_in in source :
	
	# Variable Init
	sku_me = ''
	fw_type = ''
	sku_txe = ''
	upd_rslt = ''
	fpt_in_id = ''
	found_guid = ''
	err_sps_sku = ''
	me2_type_fix = ''
	me2_type_exp = ''
	name_db_hash = ''
	eng_size_text = ''
	sku = 'NaN'
	pvpc = 'NaN'
	sku_db = 'NaN'
	rel_db = 'NaN'
	sub_sku = 'NaN'
	type_db = 'NaN'
	sku_stp = 'NaN'
	txe_sub = 'NaN'
	sps_serv = 'NaN'
	platform = 'NaN'
	sku_init = 'NaN'
	opr_mode = 'NaN'
	txe_sub_db = 'NaN'
	fuj_version = 'NaN'
	no_man_text = 'NaN'
	fit_platform = 'NaN'
	text_ubu_pre = 'NaN'
	fw_in_db_found = 'No'
	pos_sku_ker = 'Unknown'
	pos_sku_fit = 'Unknown'
	pos_sku_ext = 'Unknown'
	byp_match = None
	man_match = None
	me1_match = None
	me11_vcn_match = None
	uf_error = False
	multi_rgn = False
	upd_found = False
	unk_major = False
	rgn_exist = False
	wcod_found = False
	me_rec_ffs = False
	sku_missing = False
	rec_missing = False
	fw_type_fix = False
	fd_rgn_exist = False
	me11_sku_anl = False
	me11_ker_msg = False
	can_search_db = True
	fpt_chk_fail = False
	fpt_num_fail = False
	sps3_chk_fail = False
	fuj_rgn_exist = False
	fpt_romb_used = False
	fpt_romb_found = False
	fitc_ver_found = False
	rgn_over_extr_found = False
	err_stor = []
	note_stor = []
	warn_stor = []
	fpt_ranges = []
	fpt_matches = []
	fpt_part_all = []
	err_stor_ker = []
	p_names_store = []
	me11_vcn_ranges = []
	me11_sku_ranges = []
	man_match_ranges = []
	vcn = -1
	svn = -1
	pvbit = -1
	err_rep = 0
	rel_bit = 0
	rel_byte = 0
	mod_size = 0
	fpt_count = 0
	p_end_last = 0
	mod_end_max = 0
	fpt_num_diff = 0
	mod_size_all = 0
	cpd_end_last = 0
	fpt_chk_file = 0
	fpt_chk_calc = 0
	fpt_num_file = 0
	fpt_num_calc = 0
	p_offset_last = 0
	rec_rgn_start = 0
	fd_lock_state = 0
	sps3_chk16_file = 0
	sps3_chk16_calc = 0
	cpd_offset_last = 0
	p_end_last_cont = 0
	mod_end = 0xFFFFFFFF
	p_max_size = 0xFFFFFFFF
	eng_fw_end = 0xFFFFFFFF
	
	if not os.path.isfile(file_in) :
		if any(p in file_in for p in param.val) : continue # Next input file
		
		print(col_r + "\nError" + col_e + ": file %s was not found!" % file_in)
		
		if not param.mass_scan : mea_exit(0)
		else : continue
	
	f = open(file_in, 'rb')
	file_end = f.seek(0,2)
	file_start = f.seek(0,0)
	reading = f.read()
	
	# Show file name & extension
	if not param.ubu_mea and not param.ubu_mea_pre and not param.extr_mea and not param.print_msg :
		print("\nFile:     %s" % force_ascii(os.path.basename(file_in)))
		print("")
	elif param.ubu_mea :
		print(col_m + "\nMEA shows the Intel Engine firmware of the BIOS/SPI\n\
image that you opened with UBU. It does NOT show the\n\
current Intel Engine firmware running on your system!\n" + col_e)
		
	# UEFIFind Engine GUID Detection
	if param.enable_uf : # UEFI Strip is expected to call MEA without UEFIFind
		
		uefi_pat = "\
						header count 533A14F1EBCB3348A4DC0826E063EC08 {0}\n\
						header count A8FF90DE85B97545AB8DADE52C362CA3 {0}\n\
						header count A9A41FFC4E03D54693EEE6ECC6C7945E {0}\n\
						header count FC9137C45BE0A04A84B1F14547885C70 {0}\n\
						header count 89068D094542654F80C97F3202C5F44E {0}\n\
						header count F0D505D07598EA4A8F3996FC50DAEB94 {0}\n\
						header count 9BD5B898BAE8EE4898DDC295392F1EDB {0}\n\
						header count 390716B36513A748AECB038652E2B528 {0}\n\
						header count 0C111D82A3D0F74CAEF3E28088491704 {0}\n\
						header count 6E1F582C87B1AA4696E72081098D6413 {0}\n\
						header count 8226C7591C5C22479F25B26F4275BFEF {0}\n\
					".format(file_in).replace('	', '')
		
		try :
			with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as temp_ufpat : temp_ufpat.write(uefi_pat)
			
			uf_subp = subprocess.check_output([uf_path, "file", temp_ufpat.name, file_in])
			uf_subp = uf_subp.replace(b'\x0D\x0D\x0A', b'\x0D\x0A').replace(b'\x0D\x0A\x0D\x0A', b'\x0D\x0A').decode('utf-8')
			
			with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as temp_ufout : temp_ufout.write(uf_subp)
			
			with open(temp_ufout.name, "r+") as out_file :
				lines = out_file.readlines()
				for i in range(2, len(lines), 4) : # Start from 3rd line with a 4 line step until eof
					if 'nothing found' not in lines[i] :
						rslt = lines[i-2].strip().split()
						found_guid = switch_guid(rslt[2], "HEX2GUID")
			
		except subprocess.CalledProcessError : pass
		except : uf_error = True
		
		try :
			# noinspection PyUnboundLocalVariable
			os.remove(temp_ufpat.name)
			# noinspection PyUnboundLocalVariable
			os.remove(temp_ufout.name)
		except : pass
	
	# Detect if file has Engine firmware
	man_pat = re.compile(br'\x00\x24\x4D((\x4E\x32)|(\x41\x4E))') # .$MN2 or .$MAN detection, 0x00 adds old ME RGN support
	man_match_store = list(man_pat.finditer(reading))
	
	if len(man_match_store) :
		for m in man_match_store : man_match_ranges.append(m) # Store all Manifest ranges
		man_match = man_match_ranges[0] # Start from 1st Manifest by default
	else :
		me1_match = (re.compile(br'\x54\x65\x6B\x6F\x61\x41\x70\x70')).search(reading) # TekoaApp detection, AMT 1.x only
		if me1_match is not None : man_match = (re.compile(br'\x50\x72\x6F\x76\x69\x73\x69\x6F\x6E\x53\x65\x72\x76\x65\x72')).search(reading) # ProvisionServer detection
	
	if man_match is None :
		
		# Determine if FD exists and if Engine Region is present
		fd_exist,start_fd_match,end_fd_match = spi_fd_init()
		if fd_exist : fd_rgn_exist,me_fd_start,me_fd_size = spi_fd('region',start_fd_match,end_fd_match)
		
		# Engine Region exists but cannot be identified
		if fd_rgn_exist :
			fuj_version = fuj_umem_ver(me_fd_start) # Check if ME Region is Fujitsu UMEM compressed (me_fd_start from spi_fd function)
			
			# ME Region is Fujitsu UMEM compressed
			if fuj_version != "NaN" :
				no_man_text = "Found" + col_y + " Fujitsu Compressed " + col_e + ("Intel Engine firmware v%s" % fuj_version)
				text_ubu_pre = "Found" + col_y + " Fujitsu Compressed " + col_e + ("Intel Engine firmware v%s" % fuj_version)
				
				if param.extr_mea : no_man_text = "NaN %s_NaN_UMEM %s NaN NaN" % (fuj_version, fuj_version)
			
			# ME Region is Foxconn X58 Test?
			elif reading[me_fd_start:me_fd_start + 0x8] == b'\xD0\x3F\xDA\x00\xC8\xB9\xB2\x00' :
				no_man_text = "Found" + col_y + " Foxconn X58 Test " + col_e + "Intel Engine firmware"
				text_ubu_pre = "Found" + col_y + " Foxconn X58 Test " + col_e + "Intel Engine firmware"
				
				if param.extr_mea : no_man_text = "NaN NaN_NaN_FOX NaN NaN NaN"
			
			# ME Region is Unknown
			else :
				no_man_text = "Found" + col_y + " unidentifiable " + col_e + "Intel Engine firmware"
				text_ubu_pre = "Found" + col_y + " unidentifiable " + col_e + "Intel Engine firmware"
				
				if param.extr_mea : no_man_text = "NaN NaN_NaN_UNK NaN NaN NaN" # For UEFI Strip (-extr)
		
		# Engine Region does not exist	
		else :
			me_rec_guid = binascii.b2a_hex(reading[:0x10]).decode('utf-8').upper()
			fuj_version = fuj_umem_ver(0) # Check if ME Region is Fujitsu UMEM compressed (me_fd_start is 0x0, no SPI FD)
			fw_start_match = (re.compile(br'\x24\x46\x50\x54.\x00\x00\x00', re.DOTALL)).search(reading) # $FPT detection
			
			# Image is a ME Recovery Module of GUID 821D110C
			if me_rec_guid == "0C111D82A3D0F74CAEF3E28088491704" :
				if param.extr_mea :
					no_man_text = "NaN NaN_NaN_REC NaN NaN NaN" # For UEFI Strip (-extr)
				elif param.print_msg :
					no_man_text = col_m + "\n\nWarning: This is not a valid Intel Engine firmware image!" + col_e + \
					col_y + "\n\nNote: Further analysis not possible without manifest header." + col_e
				elif param.ubu_mea_pre :
					no_man_text = "File does not contain Intel Engine firmware"
				else :
					no_man_text = "Release:  MERecovery Module\nGUID:     821D110C-D0A3-4CF7-AEF3-E28088491704" + \
					col_m + "\n\nWarning: This is not a valid Intel Engine firmware image!" + col_e + \
					col_y + "\n\nNote: Further analysis not possible without manifest header." + col_e
			
			# Image is ME Fujitsu UMEM compressed
			elif fuj_version != "NaN" :
				no_man_text = "Found" + col_y + " Fujitsu Compressed " + col_e + ("Intel Engine firmware v%s" % fuj_version)
				text_ubu_pre = "Found" + col_y + " Fujitsu Compressed " + col_e + ("Intel Engine firmware v%s" % fuj_version)
				
				if param.extr_mea : no_man_text = "NaN %s_NaN_UMEM %s NaN NaN" % (fuj_version, fuj_version)
			
			# Image is Foxconn X58 Test?
			elif reading[0:8] == b'\xD0\x3F\xDA\x00\xC8\xB9\xB2\x00' :
				no_man_text = "Found" + col_y + " Foxconn X58 Test " + col_e + "Intel Engine firmware"
				text_ubu_pre = "Found" + col_y + " Foxconn X58 Test " + col_e + "Intel Engine firmware"
				
				if param.extr_mea : no_man_text = "NaN NaN_NaN_FOX NaN NaN NaN"
			
			# Image contains some Engine Flash Partition Table ($FPT)
			elif fw_start_match is not None :
				(start_fw_start_match, end_fw_start_match) = fw_start_match.span()
				fpt_hdr = get_struct(reading, start_fw_start_match, FPT_Header)
				
				if fpt_hdr.FitBuild != 0 and fpt_hdr.FitBuild != 65535 :
					fitc_ver = "%s.%s.%s.%s" % (fpt_hdr.FitMajor, fpt_hdr.FitMinor, fpt_hdr.FitHotfix, fpt_hdr.FitBuild)
					no_man_text = "Found" + col_y + " Unknown " + col_e + ("Intel Engine Flash Partition Table v%s" % fitc_ver)
					text_ubu_pre = "Found" + col_y + " Unknown " + col_e + ("Intel Engine Flash Partition Table v%s" % fitc_ver)
					
					if param.extr_mea : no_man_text = "NaN %s_NaN_FPT %s NaN NaN" % (fitc_ver, fitc_ver) # For UEFI Strip (-extr)
				
				else :
					no_man_text = "Found" + col_y + " Unknown " + col_e + "Intel Engine Flash Partition Table"
					text_ubu_pre = "Found" + col_y + " Unknown " + col_e + "Intel Engine Flash Partition Table"
					
					if param.extr_mea : no_man_text = "NaN NaN_NaN_FPT NaN NaN NaN" # For UEFI Strip (-extr)
				
			# Image does not contain any kind of Intel Engine firmware
			else :
				no_man_text = "File does not contain Intel Engine firmware"

		if param.extr_mea :
			if no_man_text != "NaN" : print(no_man_text)
			else : pass
		elif param.print_msg :
			if param.alt_msg_echo : print("\nMEA: %s" % no_man_text) # Rule 2, one empty line at the end
			else : print("MEA: %s\n" % no_man_text) # Rule 1, one empty line at the beginning
			if found_guid != "" :
				gen_msg(note_stor, col_y + 'Note: Detected Engine GUID %s!' % found_guid + col_e, '')
				for i in range(len(note_stor)) : print(note_stor[i])
				print("")
		elif param.ubu_mea_pre : # Must be before param.ubu_mea
			if 'File does not contain Intel Engine firmware' not in no_man_text :
				print(text_ubu_pre + ', use ME Analyzer for details!')
			else : pass
		elif param.ubu_mea :
			print("%s" % no_man_text)
			if found_guid != "" : gen_msg(note_stor, col_y + 'Note: Detected Engine GUID %s!' % found_guid + col_e, '')
			print("")
		else :
			print("%s" % no_man_text)
			if found_guid != "" : gen_msg(note_stor, col_y + 'Note: Detected Engine GUID %s!' % found_guid + col_e, '')
			
		if param.multi : multi_drop()
		else: f.close()
		
		continue # Next input file

	else : # Engine firmware found, Manifest Header ($MAN or $MN2) Analysis
		
		if binascii.b2a_hex(reading[:0x10]).decode('utf-8').upper() == "0C111D82A3D0F74CAEF3E28088491704" : me_rec_ffs = True
		
		if param.multi and param.me11_sku_disp : param.me11_sku_disp = False # dker not allowed with param.multi unless actual SKU error occurs
		
		if me1_match is None : # All except AMT 1.x
			fpt_matches = list((re.compile(br'\x24\x46\x50\x54.\x00\x00\x00', re.DOTALL)).finditer(reading))
			
			# Detect Firmware Starting Offset
			if len(fpt_matches):
				rgn_exist = True # Set Engine/$FPT detection boolean
				
				for r in fpt_matches:
					fpt_ranges.append(r.span()) # Store all $FPT ranges
					fpt_count += 1 # Count $FPT ranges
				
				# Store ranges and start from 1st $FPT by default
				(start_fw_start_match, end_fw_start_match) = fpt_ranges[0]
				
				# Multiple MERecovery 0x100 $FPT header bypass (example: Clevo)
				while reading[start_fw_start_match + 0x100:start_fw_start_match + 0x104] == b'$FPT' : # next $FPT = previous + 0x100
					start_fw_start_match += 0x100 # Adjust $FPT offset to the next header
					fpt_count -= 1 # Clevo MERecovery $FPT is ignored when reporting multiple firmware
				
				# Multiple MERecovery + GbERecovery 0x2100 $FPT header bypass (example: Clevo)
				while reading[start_fw_start_match + 0x2100:start_fw_start_match + 0x2104] == b'$FPT' : # next $FPT = previous + 0x2100
					start_fw_start_match += 0x2100 # Adjust $FPT offset to the next header
					fpt_count -= 1  # Clevo MERecovery + GbERecovery $FPT is ignored when reporting multiple firmware
					
				# Multiple MERecovery 0x1000 $FPT header bypass (example: SuperMicro)
				while reading[start_fw_start_match + 0x1000:start_fw_start_match + 0x1004] == b'$FPT' : # next $FPT = previous + 0x1000
					start_fw_start_match += 0x1000 # Adjust $FPT offset to the next header
					fpt_count -= 1 # SuperMicro MERecovery $FPT is ignored when reporting multiple firmware
				
				fpt_hdr = get_struct(reading, start_fw_start_match, FPT_Header)
				
				# Analyze $FPT header
				fpt_step = start_fw_start_match + 0x20 # 0x20 $FPT entry size
				fpt_part_num = int('%d' % fpt_hdr.NumPartitions)
				fpt_version = int('%d' % fpt_hdr.Version)
				fpt_length = int('%d' % fpt_hdr.Length)
				
				for i in range(0, fpt_part_num):
					fpt_entry = get_struct(reading, fpt_step, FPT_Entry)
					
					p_name = fpt_entry.Name
					p_owner = fpt_entry.Owner
					p_offset = fpt_entry.Offset
					p_size = fpt_entry.Size
					
					# Store all $FPT Partitions for extraction, charted
					if param.me11_mod_extr :
						fpt_start_unp = start_fw_start_match - 0x10 + p_offset
						if p_name == b'WCOD' or p_name == b'LOCL' :
							cpd_hdr = get_struct(reading, fpt_start_unp, CPD_Header)
						
							mn2_start = fpt_start_unp + 0x10 + cpd_hdr.NumModules * 0x18 # ($CPD modules start at $CPD + 0x10, size = 0x18)
							mn2_hdr = get_struct(reading, mn2_start, MN2_Manifest)
							if mn2_hdr.Tag == b'$MN2' : # Sanity check
								cpd_ext_03 = get_struct(reading, mn2_start + mn2_hdr.HeaderLength * 4, CPD_Ext_03)
								fpt_in_id = '%0.4X' % cpd_ext_03.InstanceID # LOCL/WCOD identifier
						else :
							fpt_in_id = '----'
						
						fpt_part_all.append([p_name, fpt_start_unp, fpt_start_unp + p_size, fpt_in_id])
					
					if p_name in [b'\xFF\xFF\xFF\xFF', b''] :
						p_name = '----' # If appears, wrong NumPartitions
						fpt_num_diff -= 1 # Check for less $FPT Entries
					elif p_name == b'\xE0\x15': p_name = '----' # ME8 (E0150020)
					else : p_name = p_name.decode('utf-8', 'ignore')
					
					if p_owner in [b'\xFF\xFF\xFF\xFF', b''] : p_owner = '----' # Missing
					else : p_owner = p_owner.decode('utf-8', 'ignore')
					
					if p_offset in [4294967295, 0] : p_offset_print = '----------'
					else : p_offset_print = '0x%0.8X' % p_offset
					
					if p_size in [4294967295, 0] : p_size_print = '----------'
					else : p_size_print = '0x%0.8X' % p_size
					
					if param.fpt_disp :
						print('Name: %-4s  Owner: %-4s  Offset: %s  Size: %s' % (p_name,p_owner,p_offset_print,p_size_print))
						if i == fpt_part_num - 1 : print('')
					
					# Adjust Manifest Header to Recovery section based on $FPT
					p_names_store.append(p_name) # For ME2 CODE after RCVY
					if (p_name == 'CODE' and 'RCVY' not in p_names_store) or p_name in ['RCVY', 'FTPR', 'IGRT'] :
						rec_rgn_start = start_fw_start_match + p_offset
						# Only if partition exists at file (counter-example: MERecovery, sole $FPT etc)
						if rec_rgn_start + p_size < file_end :
							man_match_init = man_match # Backup initial Manifest
							man_match = man_pat.search(reading[rec_rgn_start:rec_rgn_start + p_size])
							
							# If partition is wrong, fall back to initial Manifest (Intel ME Capsule image)
							if man_match is None :
								man_match = man_match_init
								rec_rgn_start = 0
						else :
							rec_rgn_start = 0
					
					if p_name == 'ROMB' :
						fpt_romb_found = True
						if p_offset != 0 and p_size != 0 : fpt_romb_used = True
					
					if 0 < p_offset < p_max_size and 0 < p_size < p_max_size : eng_fw_end = p_offset + p_size
					else : eng_fw_end = p_max_size
					
					# Store last partition (max offset)
					if p_offset_last < p_offset < p_max_size:
						p_offset_last = p_offset
						p_size_last = p_size
						p_end_last = eng_fw_end
					
					fpt_step += 0x20 # Next $FPT entry
			
				# Check for extra $FPT Entries, wrong NumPartitions (0x2+ for SPS3 Checksum)
				while reading[fpt_step + 0x2:fpt_step + 0xC] != b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF' :
					fpt_num_diff += 1
					fpt_step += 0x20
			
				# Check $FPT NumPartitions validity
				if fpt_num_diff != 0 :
					fpt_num_fail = True
					fpt_num_file = '0x%0.2X' % fpt_hdr.NumPartitions
					fpt_num_calc = '0x%0.2X' % (fpt_hdr.NumPartitions + fpt_num_diff)
			
			(start_man_match, end_man_match) = man_match.span()
			start_man_match += rec_rgn_start
			end_man_match += rec_rgn_start
			
			pr_man_1 = (reading[end_man_match + 0x274:end_man_match + 0x278]).decode('utf-8', 'ignore') # FTPR,OPR. (ME >= 11, TXE >= 3, SPS >= 4)
			pr_man_2 = (reading[end_man_match + 0x264:end_man_match + 0x268]).decode('utf-8', 'ignore') # FTPR,OPxx,WCOD,LOCL (6 <= ME <= 10, TXE <= 2, SPS <= 3)
			pr_man_3 = (reading[end_man_match + 0x28C:end_man_match + 0x290]).decode('utf-8', 'ignore') # BRIN (ME <= 5)
			pr_man_4 = (reading[end_man_match + 0x2DC:end_man_match + 0x2E0]).decode('utf-8', 'ignore') # EpsR,EpsF (SPS 1)
			pr_man_5 = (reading[end_man_match + 0x264:end_man_match + 0x268]).decode('utf-8', 'ignore') # IGRT (ME 6 IGN)
			pr_man_6 = (reading[end_man_match + 0x270:end_man_match + 0x277]).decode('utf-8', 'ignore') # $MMEBUP (ME 6 IGN BYP)
			pr_man_7 = (reading[end_man_match + 0x26C:end_man_match + 0x270]).decode('utf-8', 'ignore') # WCOD,LOCL (ME >= 11 Partial)
			
			# Recovery Manifest Header not found (no $FPT or wrong initial manifest), fall back to manual scanning
			if not any(p in pr_man_1 for p in ('FTPR','OPR')) and not any(p in pr_man_2 for p in ('FTPR','OP','WCOD','LOCL')) \
			and ("BRIN" not in pr_man_3) and not any(p in pr_man_4 for p in ('EpsR','EpsF')) and ("IGRT" not in pr_man_5) \
			and ("$MMEBUP" not in pr_man_6) and not any(p in pr_man_7 for p in ('WCOD','LOCL')) :
				
				if len(man_match_store) > 1 : # Extra searches only if multiple manifest exist
					pr_man = (re.compile(br'\x00\x24\x4D\x4E\x32.{628}\x46\x54\x50\x52', re.DOTALL)).search(reading) # .$MN2 + [0x274] + FTPR
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x4E\x32.{628}\x4F\x50\x52\x00', re.DOTALL)).search(reading) # .$MN2 + [0x274] + OPR.
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x4E\x32.{612}\x49\x47\x52\x54', re.DOTALL)).search(reading) # .$MN2 + [0x264] + IGRT
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x4E\x32.{612}\x46\x54\x50\x52', re.DOTALL)).search(reading) # .$MN2 + [0x264] + FTPR
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x4E\x32.{612}\x4F\x50.{2}', re.DOTALL)).search(reading) # .$MN2 + [0x264] + OPxx
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x41\x4E.{652}\x42\x52\x49\x4E', re.DOTALL)).search(reading) # .$MAN + [0x28C] + BRIN
					if pr_man is None : pr_man = (re.compile(br'\x00\x24\x4D\x41\x4E.{732}\x45\x70\x73', re.DOTALL)).search(reading) # .$MAN + [0x2DC] + Epsx
					
					# Found proper Manifest Header from Recovery section
					if pr_man is not None :
						(start_man_match, end_man_match) = pr_man.span()
						end_man_match = start_man_match + 0x5 # .$MAN/.$MN2
						
						# Check if Intel DEV_ID of 8086 is valid
						if intel_id() != 'OK' :
							print("File does not contain Intel Engine firmware")
							continue # Next input file
					else :
						print("File does not contain Intel Engine firmware")
						continue
				# Only one (initial, non-Recovery) Manifest Header exists
				else :
					print("File does not contain Intel Engine firmware")
					continue
			
			# Recovery Manifest Header found, check if Intel DEV_ID of 8086 is valid
			elif intel_id() != 'OK' :
				print("File does not contain Intel Engine firmware")
				continue # Next input file
			
			# Detect RSA Signature and Public Key
			rsa_hash,rsa_pkey = rsa_anl()
			
			# Scan $MAN/$MN2 manifest
			mn2_ftpr_hdr = get_struct(reading, start_man_match - 0x1B, MN2_Manifest)
			
			major = mn2_ftpr_hdr.Major
			minor = mn2_ftpr_hdr.Minor
			hotfix = mn2_ftpr_hdr.Hotfix
			build = mn2_ftpr_hdr.Build
			svn = mn2_ftpr_hdr.SVN_9
			vcn = mn2_ftpr_hdr.VCN
			day = '%0.2X' % mn2_ftpr_hdr.Day
			month = '%0.2X' % mn2_ftpr_hdr.Month
			year = '%0.4X' % mn2_ftpr_hdr.Year
			date = "%s-%s-%s" % (year, month, day)
			
			# Detect Firmware Variant (ME, TXE or SPS)
			variant = db_pkey()
			
			if variant == "NaN" : # Variant detection by RSA Public Key in DB failed
				# 5FB2D04BC4D8B4E90AECB5C708458F95 = RSA PKEY used at both ME & TXE PRE-BYP
				
				# ME2-5/SPS1 --> $MME = 0x50, ME6-10 & SPS2-3 --> $MME = 0x60, TXE1-2 --> $MME = 0x80
				txe3_match = (re.compile(br'\x52\x42\x45\x50\x72\x62\x65\x00\x00\x00\x00\x00')).search(reading) # RBEPrbe.....
				txe1_match = reading[end_man_match + 0x270 + 0x80:end_man_match + 0x270 + 0x84].decode('utf-8', 'ignore') # Go to 2nd $MME module
				if txe3_match is not None or txe1_match == '$MME' : variant = "TXE"
				else :
					sps_match = (re.compile(br'\x24\x43\x50\x44.\x00\x00\x00\x01\x01\x10.\x4F\x50\x52\x00', re.DOTALL)).search(reading) # $CPD + [0x8] + OPR. detection for SPS 4 OPR
					if sps_match is None : sps_match = (re.compile(br'\x62\x75\x70\x5F\x72\x63\x76\x2E\x6D\x65\x74')).search(reading) # bup_rcv.met detection for SPS 4 REC
					if sps_match is None : sps_match = (re.compile(br'\x24\x53\x4B\x55\x03\x00\x00\x00\x2F\xE4\x01\x00')).search(reading) # $SKU of SPS 2 & 3
					if sps_match is None : sps_match = (re.compile(br'\x24\x53\x4B\x55\x03\x00\x00\x00\x08\x00\x00\x00')).search(reading) # $SKU of SPS 1
					if sps_match is not None : variant = "SPS"
					else : variant = "ME" # Default, no TXE/SPS detected
			
			# Detect FTPR RSA Signature Validity
			man_valid = rsa_sig_val(mn2_ftpr_hdr, start_man_match - 0x1B)
			if not man_valid[0] :
				err_rep += 1
				err_stor.append(col_r + "Error" + col_e + ", invalid FTPR RSA Signature!" + col_r + " *" + col_e)
			
			# Detect Intel Flash Descriptor
			fd_exist,start_fd_match,end_fd_match = spi_fd_init()
			if fd_exist :
				fd_rgn_exist,me_fd_start,me_fd_size = spi_fd('region',start_fd_match,end_fd_match)
				fd_lock_state = spi_fd('unlocked',start_fd_match,end_fd_match)
			
			# Perform $FPT actions variant-dependents
			if rgn_exist :
				
				# Multiple Backup $FPT header bypass at SPS1/SPS4 (DFLT/FPTB)
				if variant == "SPS" and fpt_count == 2 and (major == 4 or major == 1) : fpt_count -= 1
				
				# Trigger multiple $FPT message after MERecovery/SPS corrections
				if fpt_count > 1 : multi_rgn = True
				
				fpt_pre_hdr = None
				fpt_chk_start = 0x0
				fpt_start = start_fw_start_match - 0x10
				fpt_chk_byte = reading[start_fw_start_match + 0xB]
				
				if fpt_version == 32 and fpt_length == 48 :
					fpt_pre_hdr = get_struct(reading, fpt_start, FPT_Pre_Header)
				elif fpt_version == 32 and fpt_length == 32 and ((variant == 'ME' and major >= 11) or (variant == 'TXE' and major >= 3) or (variant == 'SPS' and major >= 4)) :
					fpt_chk_start = 0x10 # ROMB instructions excluded
					fpt_pre_hdr = get_struct(reading, fpt_start, FPT_Pre_Header)
				elif fpt_version == 16 and fpt_length == 32 :
					fpt_start = start_fw_start_match
				
				fpt_end = fpt_start + 0x1000 # 4KB size
				
				# Check $FPT Checksum validity
				# noinspection PyUnboundLocalVariable
				fpt_chk_file = '0x%0.2X' % fpt_hdr.Checksum
				chk_sum = sum(reading[fpt_start + fpt_chk_start:fpt_start + fpt_chk_start + fpt_length]) - fpt_chk_byte
				fpt_chk_calc = '0x%0.2X' % ((0x100 - chk_sum & 0xFF) & 0xFF)
				if fpt_chk_calc != fpt_chk_file: fpt_chk_fail = True
				
				# TXE3 EXTR checksum from FIT is a placeholder (0x00), ignore
				if [variant,major,fpt_chk_fail] == ['TXE',3,True] : fpt_chk_fail = False
				
				# Check SPS3 $FPT Checksum validity (from Lordkag's UEFIStrip)
				if variant == 'SPS' and major == 3 :
					sps3_chk_start = fpt_start + 0x30
					# noinspection PyUnboundLocalVariable
					sps3_chk_end = sps3_chk_start + fpt_part_num * 0x20
					fpt_chk16 = sum(bytearray(reading[sps3_chk_start:sps3_chk_end])) & 0xFFFF
					sps3_chk16 = ~fpt_chk16 & 0xFFFF
					sps3_chk16_file = '0x%0.4X' % (int(binascii.b2a_hex( (reading[sps3_chk_end:sps3_chk_end + 0x2])[::-1] ), 16))
					sps3_chk16_calc = '0x%0.4X' % sps3_chk16
					if sps3_chk16_calc != sps3_chk16_file: sps3_chk_fail = True
				
				# Last/Uncharted partition scanning inspired by Lordkag's UEFIStrip
				# ME2-ME6 don't have size for last partition, scan its submodules
				if p_end_last == p_max_size :
					p_offset_last += fpt_start
					mn2_hdr = get_struct(reading, p_offset_last, MN2_Manifest)
					man_tag = mn2_hdr.Tag
					man_num = mn2_hdr.NumModules
					man_len = mn2_hdr.HeaderLength * 4
					mod_start = p_offset_last + man_len + 0xC
					
					# ME6
					if man_tag == b'$MN2' :

						for _ in range(0, man_num) :
							mme_mod = get_struct(reading, mod_start, MME_Header_New)
							
							mod_code_start = mme_mod.Offset_MN2
							mod_size_comp = mme_mod.SizeComp
							mod_size_uncomp = mme_mod.SizeUncomp
							
							if mod_size_comp > 0 : mod_size = mod_size_comp
							elif mod_size_comp == 0 : mod_size = mod_size_uncomp
							
							mod_end = p_offset_last + mod_code_start + mod_size
							
							if mod_end > mod_end_max : mod_end_max = mod_end # In case modules are not offset sorted
							
							mod_start += 0x60
					
					# ME2-5
					elif man_tag == b'$MAN' :
						
						for _ in range(0, man_num) :
							mme_mod = get_struct(reading, mod_start, MME_Header_Old)
							mme_tag = mme_mod.Tag
							
							if mme_tag == b'$MME' : # Sanity check
								mod_size_all += mme_mod.Size # Append all $MOD ($MME Code) sizes
								mod_end_max = mod_start + 0x50 + 0xC + mod_size_all # Last $MME + $MME size + $SKU + all $MOD sizes
								mod_end = mod_end_max
							
								mod_start += 0x50
					
					# For Engine alignment & size, remove fpt_start (included in mod_end_max < mod_end < p_offset_last)
					mod_align = (mod_end_max - fpt_start) % 0x1000 # 1K alignment on Engine size only
					
					if mod_align > 0 : eng_fw_end = mod_end + 0x1000 - mod_align - fpt_start
					else : eng_fw_end = mod_end
				
				# Last $FPT entry has size, scan for uncharted partitions
				else :
					
					# TXE3+ uncharted DNXP starts 0x1000 after last $FPT entry for some reason
					if variant == 'TXE' and major == 3 and reading[p_end_last:p_end_last + 0x4] != b'$CPD' :
						if reading[p_end_last + 0x1000:p_end_last + 0x1004] == b'$CPD' : p_end_last += 0x1000
					
					# ME8+ WCOD/LOCL but works for ME7, TXE1-2, SPS2-3 even though these end at last $FPT entry
					while reading[p_end_last + 0x1C:p_end_last + 0x20] == b'$MN2' :
						
						mn2_hdr = get_struct(reading, p_end_last, MN2_Manifest)
						man_ven = '%X' % mn2_hdr.VEN_ID
						
						if man_ven == '8086' : # Sanity check
							man_num = mn2_hdr.NumModules
							man_len = mn2_hdr.HeaderLength * 4
							mod_start = p_end_last + man_len + 0xC
							if variant in ['ME','SPS'] : mme_size = 0x60
							elif variant == "TXE" : mme_size = 0x80
							mcp_start = mod_start + man_num * mme_size + mme_size # (each $MME = mme_size, mme_size padding after last $MME)
						
							mcp_mod = get_struct(reading, mcp_start, MCP_Header) # $MCP holds total partition size
						
							if mcp_mod.Tag == b'$MCP' : # Sanity check
								p_end_last += mcp_mod.Offset_Code_MN2 + mcp_mod.CodeSize
							else :
								break # main "while" loop
						else :
							break # main "while" loop
						
					# SPS1, should not be run but works even though it ends at last $FPT entry
					while reading[p_end_last + 0x1C:p_end_last + 0x20] == b'$MAN' :
							
						mn2_hdr = get_struct(reading, p_end_last, MN2_Manifest)
						man_ven = '%X' % mn2_hdr.VEN_ID
						
						if man_ven == '8086': # Sanity check
							man_num = mn2_hdr.NumModules
							man_len = mn2_hdr.HeaderLength * 4
							mod_start = p_end_last + man_len + 0xC
							mod_size_all = 0
							
							for _ in range(0, man_num) :
								mme_mod = get_struct(reading, mod_start, MME_Header_Old)
								mme_tag = mme_mod.Tag
								
								if mme_tag == b'$MME': # Sanity check
									mod_size_all += mme_mod.Size # Append all $MOD ($MME Code) sizes
									p_end_last = mod_start + 0x50 + 0xC + mod_size_all # Last $MME + $MME size + $SKU + all $MOD sizes
								
									mod_start += 0x50
								else :
									p_end_last += 10 # to break main "while" loop
									break # nested "for" loop
						else :
							break # main "while" loop
					
					# ME11+ WCOD/LOCL, TXE3+ DNXP
					while reading[p_end_last:p_end_last + 0x4] == b'$CPD' :
						
						cpd_hdr = get_struct(reading, p_end_last, CPD_Header)
						cpd_num = cpd_hdr.NumModules
						cpd_tag = cpd_hdr.PartitionName
						
						# Calculate partition size by the $CPD Extension 03 (CPD_Ext_03)
						# PartitionSize of CPD_Ext_03 is always 0x0A at TXE3+ so check $CPD entries instead
						mn2_start = p_end_last + 0x10 + cpd_num * 0x18 # ($CPD modules start at $CPD + 0x10, size = 0x18)
						mn2_hdr = get_struct(reading, mn2_start, MN2_Manifest)
						if mn2_hdr.Tag == b'$MN2' : # Sanity check
							man_len = mn2_hdr.HeaderLength * 4
							cpd_ext_03 = get_struct(reading, mn2_start + man_len, CPD_Ext_03)
							fpt_in_id = '%0.4X' % cpd_ext_03.InstanceID # LOCL/WCOD identifier
							
							# ISHC size at $FPT can be larger than CPD_Ext_03.PartitionSize because
							# it is the last charted region and thus 1K pre-alligned by Intel at the $FPT header
							if cpd_ext_03.PartitionName == cpd_hdr.PartitionName : # Sanity check
								p_end_last_cont = cpd_ext_03.PartitionSize
							else :
								break # main "while" loop
						else :
							break # main "while" loop
							
						# Calculate partition size by the $CPD entries (TXE3+, 2nd check for ME11+)
						for entry in range(1, cpd_num, 2) : # Skip 1st .man module, check only .met
							cpd_entry_hdr = get_struct(reading, p_end_last + 0x10 + entry * 0x18, CPD_Entry)
							cpd_off_attr = format(cpd_entry_hdr.OffsetAttrib, '032b') # 32 bits (LE)
							cpd_mod_off = int(cpd_off_attr[7:], 2) # $CPD Entry Offset Attribute Address (from $CPD, 25 bits)
							cpd_entry_name = cpd_entry_hdr.Name
								
							if b'.met' not in cpd_entry_name and b'.man' not in cpd_entry_name : # Sanity check
								cpd_entry_offset = cpd_mod_off
								cpd_entry_size = cpd_entry_hdr.Size
								
								# Store last entry (max CPD offset)
								if cpd_entry_offset > cpd_offset_last :
									cpd_offset_last = cpd_entry_offset
									cpd_end_last = cpd_entry_offset + cpd_entry_size
							else :
								break # nested "for" loop
						
						fpt_off_start = p_end_last # Store starting offset of current $FPT Partition for fpt_part_all
						
						# Take the largest partition size from the two checks
						# Add previous $CPD start for next size calculation
						p_end_last += max(p_end_last_cont,cpd_end_last)
						
						# Store all $FPT Partitions, uncharted
						if param.me11_mod_extr : fpt_part_all.append([cpd_tag, fpt_off_start, p_end_last, fpt_in_id])
					
					# For Engine alignment & size, no removal of fpt_start (not included in p_end_last)
					mod_align = p_end_last % 0x1000 # 1K alignment on Engine size only
					
					if mod_align > 0 : eng_fw_end = p_end_last + 0x1000 - mod_align
					else : eng_fw_end = p_end_last
				
				# Detect SPS 4 (usually) Uncharted empty Partition ($BIS)
				if variant == 'SPS' : sps4_bis_match = (re.compile(br'\x24\x42\x49\x53\x00')).search(reading)
				else : sps4_bis_match = None
				
				# SPI image with FD (MERecovery excluded)
				if fd_rgn_exist and not me_rec_ffs :
					# noinspection PyTypeChecker
					padd_size_fd = me_fd_size - eng_fw_end
					
					if eng_fw_end > me_fd_size :
						eng_size_text = col_m + 'Warning: Firmware size exceeds Engine region, possible data loss!' + col_e
					elif eng_fw_end < me_fd_size :
						if reading[fpt_start + eng_fw_end:fpt_start + eng_fw_end + padd_size_fd] != padd_size_fd * b'\xFF' :
							# Extra data at Engine FD region padding
							if sps4_bis_match is not None : eng_size_text = ''
							else : eng_size_text = col_m + 'Warning: Data in Engine region padding, possible data corruption!' + col_e
				# Bare Engine Region
				elif fpt_start == 0 :
					# noinspection PyTypeChecker
					padd_size_file = file_end - eng_fw_end
					
					# noinspection PyTypeChecker
					if eng_fw_end > file_end :
						eng_size_text = 'Warning: Firmware size exceeds file, possible data loss!'
					elif eng_fw_end < file_end :
						if reading[eng_fw_end:eng_fw_end + padd_size_file] == padd_size_file * b'\xFF' :
							# Extra padding is clear
							eng_size_text = 'Warning: File size exceeds firmware, unneeded padding!'
						else :
							# Extra padding has data
							if sps4_bis_match is not None : eng_size_text = ''
							else : eng_size_text = 'Warning: File size exceeds firmware, data in padding!'
			
			# Firmware Type detection (Stock, Extracted, Update)
			if rgn_exist : # SPS 1-3 have their own Firmware Types
				if variant == "SPS" and major < 4 : fw_type = "Region" # SPS is built manually so EXTR
				elif variant == "ME" and (1 < major < 8) :
					# Check 1, FOVD section
					if (major > 2 and not fovd_clean("new")) or (major == 2 and not fovd_clean("old")) : fw_type = "Region, Extracted"
					else :
						# Check 2, EFFS/NVKR strings
						fitc_match = re.compile(br'\x4B\x52\x4E\x44\x00').search(reading) # KRND. detection = FITC, 0x00 adds old ME RGN support
						if fitc_match is not None :
							if major == 4 : fw_type_fix = True # ME4-Only Fix 3
							else : fw_type = "Region, Extracted"
						elif major in [2,3] : fw_type_fix = True # ME2-Only Fix 1, ME3-Only Fix 1
						else : fw_type = "Region, Stock"
				elif (variant == "ME" and major >=8) or (variant == "TXE" and major < 3) or (variant == "SPS" and major > 3) :
					# Check 1, FITC Version
					# noinspection PyUnboundLocalVariable
					fpt_hdr = get_struct(reading, start_fw_start_match, FPT_Header)
				
					if fpt_hdr.FitBuild == 0 or fpt_hdr.FitBuild == 65535 : # 0000/FFFF --> clean ME/TXE
						fw_type = "Region, Stock"
						# Check 2, FOVD section
						if not fovd_clean("new") : fw_type = "Region, Extracted"
					else :
						# Get FIT/FITC version used to build the image
						fitc_ver_found = True
						fw_type = "Region, Extracted"
						fitc_major = fpt_hdr.FitMajor
						fitc_minor = fpt_hdr.FitMinor
						fitc_hotfix = fpt_hdr.FitHotfix
						fitc_build = fpt_hdr.FitBuild
				elif variant == 'TXE' and major > 2 :
					# Extracted are created by FIT temporarily, placeholder $FPT header and checksum
					if reading[fpt_start:fpt_start + 0x10] + reading[fpt_start + 0x1C:fpt_start + 0x30] + \
					reading[fpt_start + 0x1B:fpt_start + 0x1C] == b'\xFF' * 0x24 + b'\x00' : fw_type = "Region, Extracted"
					else : fw_type = "Region, Stock"
			else :
				fw_type = "Update" # No Region detected, Update
			
			# Check for Fujitsu UMEM ME Region (RGN/$FPT or UPD/$MN2)
			if fd_rgn_exist :
				fuj_umem_spi = reading[me_fd_start:me_fd_start + 0x4]
				fuj_umem_spi = binascii.b2a_hex(fuj_umem_spi).decode('utf-8').upper()
				if fuj_umem_spi == "554DC94D" : fuj_rgn_exist = True # Futjitsu ME Region (RGN or UPD) with header UMEM
			else :
				fuj_umem_spi = reading[0x0:0x4]
				fuj_umem_spi = binascii.b2a_hex(fuj_umem_spi).decode('utf-8').upper()
				if fuj_umem_spi == "554DC94D" : fuj_rgn_exist = True
			
			# Detect Firmware Release (Production, Pre-Production, ROM-Bypass, Other)
			rel_signed = ["Production", "Debug"][(mn2_ftpr_hdr.Flags >> 31) & 1] # MSB result as list slice
			rel_flag = ["Production", "Pre-Production"][(mn2_ftpr_hdr.Flags >> 30) & 1]
			
			# Check for ROM-Bypass entry at $FPT
			if rgn_exist and fpt_romb_found :
				# Pre x86 Engine have ROMB entry at $FPT only when required, covered by fpt_romb_found
				
				if fpt_pre_hdr is not None and ((variant == "ME" and major >= 11) or (variant == "TXE" and major >= 3) or (variant == "SPS" and major >= 4)) :
					# noinspection PyUnboundLocalVariable
					byp_x86 = fpt_pre_hdr.ROMB_Instr_0 # Check x86 Engine ROM-Bypass Instruction 0
					if not fpt_romb_used and byp_x86 == 0 : fpt_romb_found = False # x86 Engine ROMB depends on $FPT Offset/Size + Instructions
			
			# PRD/PRE/BYP must be after ME-REC Module Release Detection
			if me_rec_ffs : release = "ME Recovery Module"
			elif fpt_romb_found : release = "ROM-Bypass"
			elif rel_signed == "Production" : release = "Production"
			elif rel_signed == "Debug" : release = "Pre-Production"
			else :
				release = col_r + "Error" + col_e + ", unknown firmware release!" + col_r + " *" + col_e
				err_rep += 1
				err_stor.append(release)
			
			if release == "Production" : rel_db = "PRD"
			elif release == "Pre-Production" : rel_db = "PRE"
			elif release == "ROM-Bypass" : rel_db = "BYP"
			
			# Detect Firmware $SKU (Variant, Major & Minor dependant)
			sku_pat = re.compile(br'\x24\x53\x4B\x55[\x03-\x04]\x00\x00\x00') # $SKU detection, pattern used later as well
			sku_match = sku_pat.search(reading[start_man_match:]) # Search $SKU after proper $MAN/$MN2 Manifest
			if sku_match is not None :
				(start_sku_match, end_sku_match) = sku_match.span()
				start_sku_match += start_man_match
				end_sku_match += start_man_match
			
			# Detect PV/PC bit (0 or 1)
			if (variant == "ME" and major > 7) or variant == "TXE" :
				pvbit_match = (re.compile(br'\x24\x44\x41\x54....................\x49\x46\x52\x50', re.DOTALL)).search(reading) # $DAT + [0x14] + IFRP detection
				if pvbit_match is not None :
					(start_pvbit_match, end_pvbit_match) = pvbit_match.span()
					pvbit = int(binascii.b2a_hex( (reading[start_pvbit_match + 0x10:start_pvbit_match + 0x11]) ), 16)
				elif (variant == "ME" and major > 10) or (variant == "TXE" and major > 2) :
					pvbit = int(binascii.b2a_hex( (reading[start_man_match - 0xF:start_man_match - 0xE]) ), 16)
				
				if pvbit == 0 : pvpc = "No"
				elif pvbit == 1 : pvpc = "Yes"
				else :
					pvpc = col_r + "Error" + col_e + ", unknown PV bit!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(pvpc)
		
		else : # AMT 1.x
			variant = "ME"
			(start_man_match, end_man_match) = man_match.span()
			major = int(binascii.b2a_hex( (reading[start_man_match - 0x260:start_man_match - 0x25F]) [::-1]).decode('utf-8'))
			minor = int(binascii.b2a_hex( (reading[start_man_match - 0x25F:start_man_match - 0x25E]) [::-1]).decode('utf-8'))
			hotfix = int(binascii.b2a_hex( (reading[start_man_match - 0x25E:start_man_match - 0x25D]) [::-1]).decode('utf-8'))
		
		if variant == "ME" : # Management Engine
			
			if me1_match is None and sku_match is not None : # Found $SKU entry
			
				if 1 < major < 7:
					sku_me = reading[start_sku_match + 8:start_sku_match + 0xC]
					sku_me = binascii.b2a_hex(sku_me).decode('utf-8').upper()
				elif 6 < major < 11:
					sku_me = reading[start_sku_match + 8:start_sku_match + 0x10]
					sku_me = binascii.b2a_hex(sku_me).decode('utf-8').upper()
			
			if major == 1 and me1_match is not None : # Desktop ICH7: Tekoa GbE 82573E
				print("Family:   AMT")
				print("Version:  %s.%s.%s" % (major, minor, hotfix))
				
				if found_guid != "" : gen_msg(note_stor, col_y + 'Note: Detected Engine GUID %s!' % found_guid + col_e, '')
				
				f.close()
				continue # Next input file
			
			elif major == 2 : # Desktop ICH8: 2.0 & 2.1 & 2.2 or Mobile ICH8M: 2.5 & 2.6
				if sku_me == "00000000" :
					sku = "AMT"
					sku_db = "AMT"
					if minor >= 5 : db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_2_AMTM')
					else : db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_2_AMTD')
					if minor < 2 or (minor == 2 and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
					elif minor == 5 or (minor == 6 and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "02000000" :
					sku = "QST" # Name is either QST or ASF, probably QST based on size and RGN modules
					sku_db = "QST"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_2_QST')
					if minor == 0 and (hotfix < db_hot or (hotfix == db_hot and build < db_bld)) : upd_found = True
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 2 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
				# ME2-Only Fix 1 : The usual method to detect EXTR vs RGN does not work for ME2
				if fw_type_fix :
					if sku == "QST" or (sku == "AMT" and minor >= 5) :
						nvkr_match = (re.compile(br'\x4E\x56\x4B\x52\x4B\x52\x49\x44')).search(reading) # NVKRKRID detection
						if nvkr_match is not None :
							(start_nvkr_match, end_nvkr_match) = nvkr_match.span()
							nvkr_start = int.from_bytes(reading[end_nvkr_match:end_nvkr_match + 0x4], 'little')
							nvkr_size = int.from_bytes(reading[end_nvkr_match + 0x4:end_nvkr_match + 0x8], 'little')
							nvkr_data = reading[fpt_start + nvkr_start:fpt_start + nvkr_start + nvkr_size]
							# NVKR sections : Name[0xC] + Size[0x3] + Data[Size]
							prat_match = (re.compile(br'\x50\x72\x61\x20\x54\x61\x62\x6C\x65\xFF\xFF\xFF')).search(nvkr_data) # "Pra Table" detection (2.5/2.6)
							maxk_match = (re.compile(br'\x4D\x61\x78\x55\x73\x65\x64\x4B\x65\x72\x4D\x65\x6D\xFF\xFF\xFF')).search(nvkr_data) # "MaxUsedKerMem" detection
							if prat_match is not None :
								(start_prat_match, end_prat_match) = prat_match.span()
								prat_start = fpt_start + nvkr_start + end_prat_match + 0x3
								prat_end = fpt_start + nvkr_start + end_prat_match + 0x13
								me2_type_fix = (binascii.b2a_hex(reading[prat_start:prat_end])).decode('utf-8').upper()
								me2_type_exp = "7F45DBA3E65424458CB09A6E608812B1"
							elif maxk_match is not None :
								(start_maxk_match, end_maxk_match) = maxk_match.span()
								qstpat_start = fpt_start + nvkr_start + end_maxk_match + 0x68
								qstpat_end = fpt_start + nvkr_start + end_maxk_match + 0x78
								me2_type_fix = (binascii.b2a_hex(reading[qstpat_start:qstpat_end])).decode('utf-8').upper()
								me2_type_exp = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
					elif sku == "AMT" and minor < 5 :
						nvsh_match = (re.compile(br'\x4E\x56\x53\x48\x4F\x53\x49\x44')).search(reading) # NVSHOSID detection
						if nvsh_match is not None :
							(start_nvsh_match, end_nvsh_match) = nvsh_match.span()
							nvsh_start = int.from_bytes(reading[end_nvsh_match:end_nvsh_match + 0x4], 'little')
							nvsh_size = int.from_bytes(reading[end_nvsh_match + 0x4:end_nvsh_match + 0x8], 'little')
							nvsh_data = reading[fpt_start + nvsh_start:fpt_start + nvsh_start + nvsh_size]
							netip_match = (re.compile(br'\x6E\x65\x74\x2E\x69\x70\xFF\xFF\xFF')).search(reading) # "net.ip" detection (2.0-2.2)
							if netip_match is not None :
								(start_netip_match, end_netip_match) = netip_match.span()
								netip_size = int.from_bytes(reading[end_netip_match + 0x0:end_netip_match + 0x3], 'little')
								netip_start = fpt_start + end_netip_match + 0x4 # 0x4 always 03 so after that byte for 00 search
								netip_end = fpt_start + end_netip_match + netip_size + 0x3 # (+ 0x4 - 0x1)
								me2_type_fix = (binascii.b2a_hex(reading[netip_start:netip_end])).decode('utf-8').upper()
								me2_type_exp = (binascii.b2a_hex(b'\x00' * (netip_size - 0x1))).decode('utf-8').upper()
								
					if me2_type_fix != me2_type_exp : fw_type = "Region, Extracted"
					else : fw_type = "Region, Stock"
				
				# ME2-Only Fix 2 : Identify ICH Revision B0 firmware SKUs
				me2_sku_fix = ['1C3FA8F0B5B9738E717F74F1F01D023D58085298','AB5B010215DFBEA511C12F350522E672AD8C3345','92983C962AC0FD2636B5B958A28CFA42FB430529']
				if rsa_hash in me2_sku_fix :
					sku = "AMT B0"
					sku_db = "AMT_B0"
				
				# ME2-Only Fix 3 : Detect ROMB RGN/EXTR image correctly (at $FPT v1 ROMB was before $FPT)
				if rgn_exist and release == "Pre-Production" :
					byp_pat = re.compile(br'\x24\x56\x45\x52\x02\x00\x00\x00', re.DOTALL) # $VER2... detection (ROM-Bypass)
					byp_match = byp_pat.search(reading)
					
					if byp_match is not None :
						release = "ROM-Bypass"
						rel_db = 'BYP'
						(byp_start, byp_end) = byp_match.span()
						byp_size = fpt_start - (byp_start - 0x80)
						eng_fw_end += byp_size
						if 'Data in Engine region padding' in eng_size_text : eng_size_text = ''
						
				if minor >= 5 : platform = "Mobile"
				else : platform = "Desktop"
		
			elif major == 3 : # Desktop ICH9x (All-Optional, QST) or ICH9DO (Q35, AMT): 3.0 & 3.1 & 3.2
				if sku_me == "0E000000" or sku_me == "00000000" : # 00000000 for Pre-Alpha ROMB
					sku = "AMT" # Active Management Technology --> Remote Control (Q35 only)
					sku_db = "AMT"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_3_AMT')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "06000000" :
					sku = "ASF" # Alert Standard Format --> Message Report (Q33, ex: HP dc5800)
					sku_db = "ASF"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_3_ASF')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "02000000" :
					sku = "QST" # Quiet System Technology --> Fan Control (All but optional)
					sku_db = "QST"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_3_QST')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 3 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)

				# ME3-Only Fix 1 : The usual method to detect EXTR vs RGN does not work for ME3
				if fw_type_fix :
					me3_type_fix1 = []
					me3_type_fix2a = 0x10 * 'FF'
					me3_type_fix2b = 0x10 * 'FF'
					me3_type_fix3 = 0x10 * 'FF'
					effs_match = (re.compile(br'\x45\x46\x46\x53\x4F\x53\x49\x44')).search(reading) # EFFSOSID detection
					if effs_match is not None :
						(start_effs_match, end_effs_match) = effs_match.span()
						effs_start = int.from_bytes(reading[end_effs_match:end_effs_match + 0x4], 'little')
						effs_size = int.from_bytes(reading[end_effs_match + 0x4:end_effs_match + 0x8], 'little')
						effs_data = reading[fpt_start + effs_start:fpt_start + effs_start + effs_size]
						
						me3_type_fix1 = (re.compile(br'\x4D\x45\x5F\x43\x46\x47\x5F\x44\x45\x46\x04\x4E\x56\x4B\x52')).findall(effs_data) # ME_CFG_DEF.NVKR detection (RGN have <= 2)
						me3_type_fix2 = (re.compile(br'\x4D\x61\x78\x55\x73\x65\x64\x4B\x65\x72\x4D\x65\x6D\x04\x4E\x56\x4B\x52\x7F\x78\x01')).search(effs_data) # MaxUsedKerMem.NVKR.x. detection
						me3_type_fix3 = (binascii.b2a_hex(reading[fpt_start + effs_start + effs_size - 0x20:fpt_start + effs_start + effs_size - 0x10])).decode('utf-8').upper()
						
						if me3_type_fix2 is not None :
							(start_me3f2_match, end_me3f2_match) = me3_type_fix2.span()
							me3_type_fix2a = (binascii.b2a_hex(reading[fpt_start + effs_start + end_me3f2_match - 0x30:fpt_start + effs_start + end_me3f2_match - 0x20])).decode('utf-8').upper()
							me3_type_fix2b = (binascii.b2a_hex(reading[fpt_start + effs_start + end_me3f2_match + 0x30:fpt_start + effs_start + end_me3f2_match + 0x40])).decode('utf-8').upper()

					if len(me3_type_fix1) > 2 or (0x10 * 'FF') not in me3_type_fix3 or (0x10 * 'FF') not in me3_type_fix2a or (0x10 * 'FF') not in me3_type_fix2b : fw_type = "Region, Extracted"
					else : fw_type = "Region, Stock"
				
				# ME3-Only Fix 2 : Detect AMT ROMB UPD image correctly (very vague, may not always work)
				if fw_type == "Update" and release == "Pre-Production" : # Debug Flag detected at $MAN but PRE vs BYP is needed for UPD (not RGN)
					# It seems that ROMB UPD is smaller than equivalent PRE UPD
					# min size(ASF, UPD) is 0xB0904 so 0x100000 safe min AMT ROMB
					# min size(AMT, UPD) is 0x190904 so 0x185000 safe max AMT ROMB
					# min size(QST, UPD) is 0x2B8CC so 0x40000 safe min for ASF ROMB
					# min size(ASF, UPD) is 0xB0904 so 0xAF000 safe max for ASF ROMB
					# min size(QST, UPD) is 0x2B8CC so 0x2B000 safe max for QST ROMB
					# noinspection PyTypeChecker
					if sku == "AMT" and int(0x100000) < file_end < int(0x185000):
						release = "ROM-Bypass"
						rel_db = "BYP"
					elif sku == "ASF" and int(0x40000) < file_end < int(0xAF000):
						release = "ROM-Bypass"
						rel_db = "BYP"
					elif sku == "QST" and file_end < int(0x2B000) :
						release = "ROM-Bypass"
						rel_db = "BYP"
				
				# ME3-Only Fix 3 : Detect Pre-Alpha ($FPT v1) ROMB RGN/EXTR image correctly
				if rgn_exist and fpt_version == 16 and release == "Pre-Production" :
					byp_pat = byp_pat = re.compile(br'\x24\x56\x45\x52\x03\x00\x00\x00', re.DOTALL) # $VER3... detection (ROM-Bypass)
					byp_match = byp_pat.search(reading)
					
					if byp_match is not None :
						release = "ROM-Bypass"
						rel_db = "BYP"
						(byp_start, byp_end) = byp_match.span()
						byp_size = fpt_start - (byp_start - 0x80)
						eng_fw_end += byp_size
						if 'Data in Engine region padding' in eng_size_text : eng_size_text = ''
				
				platform = "Desktop"
		
			elif major == 4 : # Mobile ICH9M or ICH9M-E (AMT or TPM+AMT): 4.0 & 4.1 & 4.2 , xx00xx --> 4.0 , xx20xx --> 4.1 or 4.2
				if sku_me == "AC200000" or sku_me == "AC000000" or sku_me == "04000000" : # 040000 for Pre-Alpha ROMB
					sku = "AMT + TPM" # CA_ICH9_REL_ALL_SKUs_ (TPM + AMT)
					sku_db = "ALL"
				elif sku_me == "8C200000" or sku_me == "8C000000" or sku_me == "0C000000" : # 0C000000 for Pre-Alpha ROMB
					sku = "AMT" # CA_ICH9_REL_IAMT_ (AMT)
					sku_db = "AMT"
				elif sku_me == "A0200000" or sku_me == "A0000000" :
					sku = "TPM" # CA_ICH9_REL_NOAMT_ (TPM)
					sku_db = "TPM"
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 4 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
				# ME4-Only Fix 1 : Detect ROMB UPD image correctly
				if fw_type == "Update" :
					byp_pat = re.compile(br'\x52\x4F\x4D\x42') # ROMB detection (ROM-Bypass)
					byp_match = byp_pat.search(reading)
					if byp_match is not None :
						release = "ROM-Bypass"
						rel_db = "BYP"
				
				# ME4-Only Fix 2 : Detect SKUs correctly, only for Pre-Alpha firmware
				if minor == 0 and hotfix == 0 :
					if fw_type == "Update" :
						tpm_tag = (re.compile(br'\x24\x4D\x4D\x45........................\x54\x50\x4D', re.DOTALL)).search(reading) # $MME + [0x18] + TPM
						amt_tag = (re.compile(br'\x24\x4D\x4D\x45........................\x4D\x4F\x46\x46\x4D\x31\x5F\x4F\x56\x4C', re.DOTALL)).search(reading) # $MME + [0x18] + MOFFM1_OVL
					else :
						tpm_tag = (re.compile(br'\x4E\x56\x54\x50\x54\x50\x49\x44')).search(reading) # NVTPTPID partition found at ALL or TPM
						amt_tag = (re.compile(br'\x4E\x56\x43\x4D\x41\x4D\x54\x43')).search(reading) # NVCMAMTC partition found at ALL or AMT
					
					if tpm_tag is not None and amt_tag is not None :
						sku = "AMT + TPM" # CA_ICH9_REL_ALL_SKUs_
						sku_db = "ALL"
					elif tpm_tag is not None :
						sku = "TPM" # CA_ICH9_REL_NOAMT_
						sku_db = "TPM"
					else :
						sku = "AMT" # CA_ICH9_REL_IAMT_
						sku_db = "AMT"
				
				# ME4-Only Fix 3 : The usual method to detect EXTR vs RGN does not work for ME4, KRND. not enough
				if fw_type_fix :
					effs_match = (re.compile(br'\x45\x46\x46\x53\x4F\x53\x49\x44')).search(reading) # EFFSOSID detection
					if effs_match is not None :
						(start_effs_match, end_effs_match) = effs_match.span()
						effs_start = int.from_bytes(reading[end_effs_match:end_effs_match + 0x4], 'little')
						effs_size = int.from_bytes(reading[end_effs_match + 0x4:end_effs_match + 0x8], 'little')
						effs_data = reading[fpt_start + effs_start:fpt_start + effs_start + effs_size]
					
						me4_type_fix1 = (re.compile(br'\x4D\x45\x5F\x43\x46\x47\x5F\x44\x45\x46')).findall(effs_data) # ME_CFG_DEF detection (RGN have 2-4)
						me4_type_fix2 = (re.compile(br'\x47\x50\x49\x4F\x31\x30\x4F\x77\x6E\x65\x72')).search(effs_data) # GPIO10Owner detection
						me4_type_fix3 = (re.compile(br'\x41\x70\x70\x52\x75\x6C\x65\x2E\x30\x33\x2E\x30\x30\x30\x30\x30\x30')).search(effs_data) # AppRule.03.000000 detection
					
					# noinspection PyUnboundLocalVariable
					if len(me4_type_fix1) > 5 or me4_type_fix2 is not None or me4_type_fix3 is not None : fw_type = "Region, Extracted"
					else : fw_type = "Region, Stock"
				
				# Placed here in order to comply with Fix 2 above in case it is triggered
				if sku_db == "ALL" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_4_ALL')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_db == "AMT" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_4_AMT')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_db == "TPM" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_4_TPM')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
					
				platform = "Mobile"
					
			elif major == 5 : # Desktop ICH10D: Basic or ICH10DO: Professional SKUs
				if sku_me == "3E080000" : # EL_ICH10_SKU1
					sku = "Digital Office" # AMT
					sku_db = "DO"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_5_DO')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "060D0000" : # EL_ICH10_SKU4
					sku = "Base Consumer" # NoAMT
					sku_db = "BC"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_5_BC')
					if minor < db_min or (minor == db_min and hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku_me == "06080000" : # EL_ICH10_SKU2 or EL_ICH10_SKU3
					sku = "Digital Home or Base Corporate (?)"
					sku_db = "DHBC"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_5_DHBC')
					if minor < db_min or (minor == db_min and hotfix == db_hot and build < db_bld) : upd_found = True
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 5 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
					
				# ME5-Only Fix : Detect ROMB UPD image correctly
				if fw_type == "Update" :
					byp_pat = re.compile(br'\x52\x4F\x4D\x42') # ROMB detection (ROM-Bypass)
					byp_match = byp_pat.search(reading)
					if byp_match is not None :
						release = "ROM-Bypass"
						rel_db = "BYP"
				
				platform = "Desktop"
		
			elif major == 6 :
				if sku_me == "00000000" : # Ignition (128KB, 2MB)
					sku = "Ignition"
					if hotfix != 50 : # P55, PM55, 34xx (Ibex Peak)
						sku_db = "IGN_IP"
						platform = "Ibex Peak"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_6_IGNIP')
						if minor == db_min and hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif hotfix == 50 : # 89xx (Cave/Coleto Creek)
						sku_db = "IGN_CC"
						platform = "Cave/Coleto Creek"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_6_IGNCC')
						if minor == db_min and hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku_me == "701C0000" : # Home IT (1.5MB, 4MB)
					sku = "1.5MB"
					sku_db = "1.5MB"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_6_15MB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				# xxDCxx = 6.x, xxFCxx = 6.0, xxxxEE = Mobile, xxxx6E = Desktop, F7xxxx = Old Alpha/Beta Releases
				elif sku_me == "77DCEE00" or sku_me == "77FCEE00" or sku_me == "F7FEFE00" : # vPro (5MB, 8MB)
					sku = "5MB MB"
					sku_db = "5MB_MB"
					platform = "Mobile"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_6_5MBMB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "77DC6E00" or sku_me == "77FC6E00" or sku_me == "F7FE7E00" : # vPro (5MB, 8MB)
					sku = "5MB DT"
					sku_db = "5MB_DT"
					platform = "Desktop"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_6_5MBDT')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 6 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
				# ME6-Only Fix 1 : ME6 Ignition does not work with KRND
				if sku == 'Ignition' and rgn_exist :
					ign_pat = (re.compile(br'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x6D\x3C\x75\x6D')).findall(reading) # Clean $MINIFAD checksum
					if len(ign_pat) < 2 : fw_type = "Region, Extracted" # 2 before NFTP & IGRT
					else : fw_type = "Region, Stock"
				
				# ME6-Only Fix 2 : Ignore errors at ROMB (Region present, FTPR tag & size missing)
				if release == "ROM-Bypass" :
					err_rep -= 1
					rec_missing = False
					if 'Firmware size exceeds file' in eng_size_text : eng_size_text = ''
				
			elif major == 7 :
			
				# ME7.1 firmware had two SKUs (1.5MB or 5MB) for each platform: Cougar Point (6-series) or Patsburg (C600,X79)
				# After 7.1.50.1172 both platforms were merged into one firmware under the PBG SKU
				# Firmware 7.1.21.1134 is PBG-exclusive according to documentation. All 7.1.21.x releases, if any more exist, seem to be PBG-only
				# All firmware between 7.1.20.x and 7.1.41.x (excluding 7.1.21.x, 7.1.22.x & 7.1.20.1056) are CPT-only BUT with the PBG SKU
				# So basically every firmware after 7.1.20.x has the PBG SKU but only after 7.1.50.x are the platforms truly merged (CPT+PBG)
				# All firmware between 7.1.22.x (last PBG) and 7.1.30.x ("new_SKU_based_on_PBG" CPT) need to be investigated manually if they exist
				# All firmware between 7.1.41.x (last I found) and 7.1.50.x (first merged) need to be investigated manually if they exist
			
				if sku_me == "701C000103220000" or sku_me == "701C100103220000" : # 1.5MB (701C), 7.0.x (0001) or 7.1.x (1001) , CPT (0322)
					sku = "1.5MB"
					sku_db = "1.5MB_CPT"
					platform = "CPT"
				elif sku_me == "701C000183220000" or sku_me == "701C100183220000" : # 1.5MB (701C), 7.0.x (0001) or 7.1.x (1001) , PBG (8322)
					sku = "1.5MB"
					sku_db = "1.5MB_PBG"
					platform = "PBG"
				elif sku_me == "701C008103220000" : # 1.5MB (701C), Apple MAC 7.0.x (0081), CPT (0322)
					sku = "1.5MB Apple MAC" # Special Apple MAC SKU v7.0.1.1205
					sku_db = "1.5MB_MAC"
					platform = "CPT"
				elif sku_me == "775CEF0D0A430000" or sku_me == "775CFF0D0A430000" or sku_me == "77DCFF0101000000" : # 5MB (775C), 7.0.x (EF0D) or 7.1.x (FF0D) , CPT (0A43)
					# Special SKU for 5MB ROMB Alpha2 firmware v7.0.0.1041 --> 77DCFF010100
					sku = "5MB"
					sku_db = "5MB_CPT"
					platform = "CPT"
				elif sku_me == "775CEF0D8A430000" or sku_me == "775CFF0D8A430000" : # 5MB (775C), 7.0.x (EF0D) or 7.1.x (FF0D) , PBG (8A43)
					sku = "5MB"
					sku_db = "5MB_PBG"
					platform = "PBG"
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 7 SKU!" + col_r + " *" + col_e
					platform = col_r + "Error" + col_e + ", this firmware requires investigation!" + col_r + " *" + col_e
					if minor != 1 and hotfix != 20 and build != 1056 : # Exception for firmware 7.1.20.1056 Alpha (check below)
						err_rep += 1
						err_stor.append(sku)
						err_stor.append(platform)
				
				if sku_me == "701C100103220000" or sku_me == "701C100183220000": # 1.5MB (701C) , 7.1.x (1001) , CPT or PBG (0322 or 8322)
					if (20 < hotfix < 30 and hotfix != 21 and build != 1056) or (41 < hotfix < 50) : # Versions that, if exist, require manual investigation
						sku = "1.5MB"
						sku_db = "NaN"
						platform = col_r + "Error" + col_e + ", this firmware requires investigation!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(platform)
					elif 20 <= hotfix <= 41 and hotfix != 21 and build != 1056 : # CPT firmware but with PBG SKU (during the "transition" period)
						sku = "1.5MB"
						sku_db = "1.5MB_CPT"
						platform = "CPT"
					elif hotfix >= 50 : # Firmware after 7.1.50.1172 are merged CPT + PBG images with PBG SKU
						sku = "1.5MB"
						sku_db = "1.5MB_ALL"
						platform = "CPT/PBG"
				if sku_me == "775CFF0D0A430000" or sku_me == "775CFF0D8A430000": # 5MB (775C) , 7.1.x (FF0D) , CPT or PBG (0A43 or 8A43)
					if (20 < hotfix < 30 and hotfix != 21 and build != 1056 and build != 1165) or (41 < hotfix < 50) : # Versions that, if exist, require manual investigation
						sku = "5MB"
						sku_db = "NaN"
						platform = col_r + "Error" + col_e + ", this firmware requires investigation!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(platform)
					elif 20 <= hotfix <= 41 and hotfix != 21 and build != 1056 and build != 1165 : # CPT firmware but with PBG SKU (during the "transition" period)
						sku = "5MB"
						sku_db = "5MB_CPT"
						platform = "CPT"
					elif hotfix >= 50 : # Firmware after 7.1.50.1172 are merged CPT + PBG images with PBG SKU
						sku = "5MB"
						sku_db = "5MB_ALL"
						platform = "CPT/PBG"
				
				# Firmware 7.1.20.1056 Alpha is PBG with CPT SKU at PRD and unique SKU at BYP, hardcoded values
				if build == 1056 and hotfix == 20 and minor == 1 :
					sku_me7a = reading[start_sku_match + 8:start_sku_match + 0xA]
					sku_me7a = binascii.b2a_hex(sku_me7a).decode('utf-8').upper()
					if sku_me7a == "701C" :
						sku = "1.5MB"
						sku_db = "1.5MB_PBG"
						platform = "PBG"
					elif sku_me7a == "775C" :
						sku = "5MB"
						sku_db = "5MB_PBG"
						platform = "PBG"
					else :
						sku = col_r + "Error" + col_e + ", unknown ME 7 SKU!" + col_r + " *" + col_e
						platform = col_r + "Error" + col_e + ", this firmware requires investigation!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
						err_stor.append(platform)
				
				if sku == "1.5MB" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_7_15MB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku == "5MB" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_7_5MB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				if sku_db == "1.5MB_MAC" :
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_7_MAC')
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				
				# ME7 Blacklist Table Detection
				me7_blist_1_minor  = int(binascii.b2a_hex( (reading[start_man_match + 0x6DF:start_man_match + 0x6E1]) [::-1]), 16)
				me7_blist_1_hotfix = int(binascii.b2a_hex( (reading[start_man_match + 0x6E1:start_man_match + 0x6E3]) [::-1]), 16)
				me7_blist_1_build  = int(binascii.b2a_hex( (reading[start_man_match + 0x6E3:start_man_match + 0x6E5]) [::-1]), 16)
				me7_blist_2_minor  = int(binascii.b2a_hex( (reading[start_man_match + 0x6EB:start_man_match + 0x6ED]) [::-1]), 16)
				me7_blist_2_hotfix = int(binascii.b2a_hex( (reading[start_man_match + 0x6ED:start_man_match + 0x6EF]) [::-1]), 16)
				me7_blist_2_build  = int(binascii.b2a_hex( (reading[start_man_match + 0x6EF:start_man_match + 0x6F1]) [::-1]), 16)
				
				# ME7-Only Fix: ROMB UPD detection
				if fw_type == "Update" :
					me7_mn2_hdr_len = mn2_ftpr_hdr.HeaderLength * 4
					me7_mn2_mod_len = (mn2_ftpr_hdr.NumModules + 1) * 0x60
					me7_mcp = get_struct(reading, start_man_match - 0x1B + me7_mn2_hdr_len + 0xC + me7_mn2_mod_len, MCP_Header) # Goto $MCP
					
					if me7_mcp.CodeSize == 374928 or me7_mcp.CodeSize == 419984 : # 1.5/5MB ROMB Code Sizes
						release = "ROM-Bypass"
						rel_db = 'BYP'
			
			elif major == 8 :
				if sku_me == "E01C11C103220000" or sku_me == "E01C114103220000" or sku_me == "601C114103220000" :
					sku = "1.5MB"
					sku_db = "1.5MB"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_8_15MB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				elif sku_me == "FF5CFFCD0A430000" or sku_me == "FF5CFF4D0A430000" or sku_me == "7F5CFF0D0A430000" or sku_me == "7F5CFF8D0A430000" :
					# SKU for 8.1.0.1035 Alpha firmware --> 7F5CFF8D0A430000
					sku = "5MB"
					sku_db = "5MB"
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_8_5MB')
					if minor < db_min or (minor == db_min and (hotfix < db_hot or (hotfix == db_hot and build < db_bld))) : upd_found = True
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 8 SKU!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
					
				# ME8-Only Fix: SVN location
				# noinspection PyUnboundLocalVariable
				svn = mn2_ftpr_hdr.SVN_8
				
				platform = "PPT"
			
			elif major == 9 :
				if minor == 0 :
					if sku_me == "E09911C113220000" :
						sku = "1.5MB"
						sku_db = "1.5MB"
					elif sku_me == "EFD9FFCD0A430000" :
						sku = "5MB"
						sku_db = "5MB"
					else :
						sku = col_r + "Error" + col_e + ", unknown ME 9.0 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
					
					upd_found = True # 9.1 upgradable
					
					platform = "LPT"
					
				elif minor == 1 :
					if sku_me == "E09911D113220000" :
						sku = "1.5MB"
						sku_db = "1.5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_91_15MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif sku_me == "EFD9FFDD0A430000" :
						sku = "5MB"
						sku_db = "5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_91_5MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					else :
						sku = col_r + "Error" + col_e + ", unknown ME 9.1 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
					
					platform = "LPT/WPT"
					
				elif minor in [5,6] :
					if sku_me == "609A11B113220000" :
						sku = "1.5MB"
						sku_db = "1.5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_95_15MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif sku_me == "6FDAFFBD0A430000" or sku_me == "EFDAFFED0A430000" : # 2nd SKU is for old Pre-Alpha releases (ex: v9.5.0.1225)
						sku = "5MB"
						sku_db = "5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_95_5MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif sku_me == "401A001123220000" : # Special Apple MAC SKU
						sku = "1.5MB Apple Mac"
						sku_db = "1.5MB_MAC"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_95_MAC')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True 
					else :
						sku = col_r + "Error" + col_e + ", unknown ME 9.5 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
					
					# Ignore: 9.6.x (Intel Harris Beach Ultrabook, HSW developer preview)
					# https://bugs.freedesktop.org/show_bug.cgi?id=90002
					if minor == 6 : upd_found = True
					
					platform = "LPT-LP"
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 9.x Minor version!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
			elif major == 10 :
				if minor == 0 :
					if sku_me == "C0BA11F113220000" or sku_me == "C0BA11F114220000" : # 2nd SKU is BYP
						sku = "1.5MB"
						sku_db = "1.5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_100_15MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif sku_me == "CFFAFFFF0A430000" or sku_me == "CFFAFFFF0A430000" :
						sku = "5MB"
						sku_db = "5MB"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_100_5MB')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					elif sku_me == "401A001122220000" : # Special Apple MAC SKU
						sku = "1.5MB Apple Mac"
						sku_db = "1.5MB_MAC"
						db_maj,db_min,db_hot,db_bld = check_upd('Latest_ME_100_MAC')
						if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					else :
						sku = col_r + "Error" + col_e + ", unknown ME 10.0 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
					platform = "WPT-LP"
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 10.x Minor version!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
			
			elif major == 11 :
				
				sku_check,me11_sku_ranges = krod_anl() # Detect FIT SKU
				
				cpd_offset,cpd_mod_attr,cpd_ext_attr,vcn,fw_0C_sku1,fw_0C_lbg,fw_0C_sku2 = ext_anl('$MN2', start_man_match) # Detect x86 Attributes
				
				# Set SKU Type via Extension 0C Attributes
				if fw_0C_sku1 == 0 :
					sku_init = 'Corporate' # 0 Corporate/Intel (1272K MFS)
					sku_init_db = 'COR'
				elif fw_0C_sku1 == 1 : # 1 Consumer/Intel (400K MFS)
					sku_init = 'Consumer'
					sku_init_db = 'CON'
				elif fw_0C_sku1 == 2 : # 2 Slim/Apple (256K MFS)
					sku_init = 'Slim'
					sku_init_db = 'SLM'
				
				# Set SKU Platform via Extension 0C Attributes (>= 11.0.0.1205)
				if (minor == 0 and (hotfix > 0 or (hotfix == 0 and build >= 1205))) or minor > 0 :
					if fw_0C_sku2 == 0 : pos_sku_ext = 'H'
					elif fw_0C_sku2 == 1 : pos_sku_ext = 'LP'
				else : pos_sku_ext = 'Invalid'
				
				# Set Lewisburg support via Extension 0C Attributes
				if fw_0C_lbg == 0 : lbg_support = 'No'
				elif fw_0C_lbg == 1 : lbg_support = 'Yes'
				else : lbg_support = 'Unknown'
				
				ker_start,ker_end = mod_anl('anl', cpd_offset, cpd_mod_attr, cpd_ext_attr, '') # Module Analysis for all 11.x
				
				db_sku_chk,sku,sku_stp,sku_pdm = db_skl(variant) # Retreive SKU & Rev from DB
				
				# Some early firmware are reported as PRD even though they are PRE
				if release == "Production" and rsa_pkey == "5FB2D04BC4D8B4E90AECB5C708458F95" :
					release = "Pre-Production"
					rel_db = 'PRE'
				
				# Kernel Analysis for all 11.x
				ker_sku = reading[ker_start + 0x700:ker_start + 0x900] # Actual range is 0x780 - 0x840
						
				match_1_h = (re.compile(br'\x56\xA6\xF5\x9A\xC4\xA6\xDB\x69\x3C\x7A\x15')).search(ker_sku)
				match_1_lp = (re.compile(br'\x56\xA6\xF5\x9A\xC4\xA6\xDB\x69\x3C\x7A\x11')).search(ker_sku)
				
				match_2_h = (re.compile(br'\x6A\x6F\x59\xAC\x4A\x6D\xB6\x93\xC7\xA1\x50')).search(ker_sku)
				match_2_lp = (re.compile(br'\x6A\x6F\x59\xAC\x4A\x6D\xB6\x93\xC7\xA1\x11')).search(ker_sku)
				
				match_3_h = (re.compile(br'\xAB\x53\x7A\xCD\x62\x53\x6D\xB4\x9E\x3D\x0A')).search(ker_sku)
				match_3_lp = (re.compile(br'\xAB\x53\x7A\xCD\x62\x53\x6D\xB4\x9E\x3D\x08')).search(ker_sku)
						
				match_4_h = (re.compile(br'\xB5\x37\xAC\xD6\x25\x36\xDB\x49\xE3\xD0\xA8')).search(ker_sku)
				match_4_lp = (re.compile(br'\xB5\x37\xAC\xD6\x25\x36\xDB\x49\xE3\xD0\x88')).search(ker_sku)
					
				match_5_h = (re.compile(br'\x5A\x9B\xD6\x6B\x12\x9B\x6D\xA4\xF1\xE8\x54')).search(ker_sku)
				match_5_lp = (re.compile(br'\x5A\x9B\xD6\x6B\x12\x9B\x6D\xA4\xF1\xE8\x44')).search(ker_sku)
					
				match_6_h = (re.compile(br'\xA9\xBD\x66\xB1\x29\xB6\xDA\x4F\x1E\x85\x42')).search(ker_sku)
				#match_6_lp = (re.compile(br'\xA9\xBD\x66\xB1\x29\xB6\xDA\x4F\x1E\x85\xXX')).search(ker_sku)

				#match_7_h = (re.compile(br'\xA9\xBD\x66\xB1\x29\xB6\xDA\x4F\x1E\x84\xXX')).search(ker_sku)
				match_7_lp = (re.compile(br'\xA9\xBD\x66\xB1\x29\xB6\xDA\x4F\x1E\x84\x46')).search(ker_sku)
					
				match_8_h = (re.compile(br'\xAD\x4D\xEB\x35\x89\x4D\xB6\xD2\x78\xF4\x2A')).search(ker_sku)
				match_8_lp = (re.compile(br'\xAD\x4D\xEB\x35\x89\x4D\xB6\xD2\x78\xF4\x22')).search(ker_sku)
						
				match_9_h = (re.compile(br'\xD4\xDE\xB3\x58\x94\xDB\x6D\x27\x8F\x42\xA1')).search(ker_sku)
				match_9_lp = (re.compile(br'\xD4\xDE\xB3\x58\x94\xDB\x6D\x27\x8F\x42\x23')).search(ker_sku)
				
				if any(m is not None for m in (match_1_h,match_2_h,match_3_h,match_4_h,match_5_h,match_6_h,match_8_h,match_9_h)) : pos_sku_ker = "H"
				elif any(m is not None for m in (match_1_lp,match_2_lp,match_3_lp,match_4_lp,match_5_lp,match_7_lp,match_8_lp,match_9_lp)) : pos_sku_ker = "LP"
				
				# FIT Platform SKU for all 11.x
				if sku_check != "NaN" :
						
					while fit_platform == "NaN" :
						
						# 3rd byte of 1st pattern is SKU Category from 0+ (ex: 91 01 04 80 00 --> 5th, 91 01 03 80 00 --> 4th)
						if any(s in sku_check for s in (' 2C 01 03 80 00 ',' 02 D1 02 2C ')) : fit_platform = "PCH-H No Emulation KBL"
						elif any(s in sku_check for s in (' 2D 01 03 80 00 ',' 02 D1 02 2D ')) : fit_platform = "PCH-H Q270"
						elif any(s in sku_check for s in (' 2E 01 03 80 00 ',' 02 D1 02 2E ')) : fit_platform = "PCH-H Q250"
						elif any(s in sku_check for s in (' 2F 01 03 80 00 ',' 02 D1 02 2F ')) : fit_platform = "PCH-H B250"
						elif any(s in sku_check for s in (' 30 01 03 80 00 ',' 02 D1 02 30 ')) : fit_platform = "PCH-H H270"
						elif any(s in sku_check for s in (' 31 01 03 80 00 ',' 02 D1 02 31 ')) : fit_platform = "PCH-H Z270"
						elif any(s in sku_check for s in (' 32 01 01 80 00 ',' 02 D1 02 32 ')) : fit_platform = "PCH-H QMU185"
						elif any(s in sku_check for s in (' 64 00 01 80 00 ',' 02 D1 02 64 ')) : fit_platform = "PCH-H Q170"
						elif any(s in sku_check for s in (' 65 00 01 80 00 ',' 02 D1 02 65 ')) : fit_platform = "PCH-H Q150"
						elif any(s in sku_check for s in (' 66 00 01 80 00 ',' 02 D1 02 66 ')) : fit_platform = "PCH-H B150"
						elif any(s in sku_check for s in (' 67 00 01 80 00 ',' 02 D1 02 67 ')) : fit_platform = "PCH-H H170"
						elif any(s in sku_check for s in (' 68 00 01 80 00 ',' 02 D1 02 68 ')) : fit_platform = "PCH-H Z170"
						elif any(s in sku_check for s in (' 69 00 01 80 00 ',' 02 D1 02 69 ')) : fit_platform = "PCH-H H110"
						elif any(s in sku_check for s in (' 6A 00 01 80 00 ',' 02 D1 02 6A ')) : fit_platform = "PCH-H QM170"
						elif any(s in sku_check for s in (' 6B 00 01 80 00 ',' 02 D1 02 6B ')) : fit_platform = "PCH-H HM170"
						elif any(s in sku_check for s in (' 6C 00 01 80 00 ',' 02 D1 02 6C ')) : fit_platform = "PCH-H No Emulation SKL"
						elif any(s in sku_check for s in (' 6D 00 01 80 00 ',' 02 D1 02 6D ')) : fit_platform = "PCH-H C236"
						elif any(s in sku_check for s in (' 6E 00 01 80 00 ',' 02 D1 02 6E ')) : fit_platform = "PCH-H CM236"
						elif any(s in sku_check for s in (' 6F 00 01 80 00 ',' 02 D1 02 6F ')) : fit_platform = "PCH-H C232"
						elif any(s in sku_check for s in (' 70 00 01 80 00 ',' 02 D1 02 70 ')) : fit_platform = "PCH-H QMS180"
						elif any(s in sku_check for s in (' 71 00 01 80 00 ',' 02 D1 02 71 ')) : fit_platform = "PCH-H QMS185"
						elif any(s in sku_check for s in (' 90 01 04 80 00 ',' 02 D1 02 90 ')) : fit_platform = "PCH-H No Emulation BSF"
						elif any(s in sku_check for s in (' 91 01 04 80 00 ',' 91 01 03 80 00 ',' 02 D1 02 91 ')) : fit_platform = "PCH-H C422" # moved at 11.7
						elif any(s in sku_check for s in (' 92 01 04 80 00 ',' 92 01 03 80 00 ',' 02 D1 02 92 ')) : fit_platform = "PCH-H X299" # moved at 11.7
						elif any(s in sku_check for s in (' 93 01 01 80 00 ',' 02 D1 02 93 ')) : fit_platform = "PCH-H QM175"
						elif any(s in sku_check for s in (' 94 01 01 80 00 ',' 02 D1 02 94 ')) : fit_platform = "PCH-H HM175"
						elif any(s in sku_check for s in (' 95 01 01 80 00 ',' 02 D1 02 95 ')) : fit_platform = "PCH-H CM238"
						elif any(s in sku_check for s in (' C8 00 02 80 00 ',' 04 11 06 C8 ')) : fit_platform = "PCH-H C621"
						elif any(s in sku_check for s in (' C9 00 02 80 00 ',' 04 11 06 C9 ')) : fit_platform = "PCH-H C622"
						elif any(s in sku_check for s in (' CA 00 02 80 00 ',' 04 11 06 CA ')) : fit_platform = "PCH-H C624"
						elif any(s in sku_check for s in (' CB 00 02 80 00 ',' 04 11 06 CB ')) : fit_platform = "PCH-H No Emulation LBG"
						elif any(s in sku_check for s in (' F4 01 05 80 00 ',' 02 D1 02 F4 ')) : fit_platform = "PCH-H Z370"
						elif any(s in sku_check for s in (' F5 01 05 80 00 ',' 02 D1 02 F5 ')) : fit_platform = "PCH-H No Emulation Z370"
						elif any(s in sku_check for s in (' 01 00 00 80 00 ',' 02 B0 02 01 ',' 02 D0 02 01 ')) : fit_platform = "PCH-LP Premium U SKL"
						elif any(s in sku_check for s in (' 02 00 00 80 00 ',' 02 B0 02 02 ',' 02 D0 02 02 ')) : fit_platform = "PCH-LP Premium Y SKL"
						elif any(s in sku_check for s in (' 03 00 00 80 00 ',' 02 B0 02 03 ',' 02 D0 02 03 ')) : fit_platform = "PCH-LP No Emulation"
						elif any(s in sku_check for s in (' 04 00 00 80 00 ',' 02 B0 02 04 ',' 02 D0 02 04 ')) : fit_platform = "PCH-LP Base U KBL"
						elif any(s in sku_check for s in (' 05 00 00 80 00 ',' 02 B0 02 05 ',' 02 D0 02 05 ')) : fit_platform = "PCH-LP Premium U KBL"
						elif any(s in sku_check for s in (' 06 00 00 80 00 ',' 02 B0 02 06 ',' 02 D0 02 06 ')) : fit_platform = "PCH-LP Premium Y KBL"
						elif any(s in sku_check for s in (' 07 00 00 80 00 ',' 02 B0 02 07 ',' 02 D0 02 07 ')) : fit_platform = "PCH-LP Base U KBL-R"
						elif any(s in sku_check for s in (' 08 00 00 80 00 ',' 02 B0 02 08 ',' 02 D0 02 08 ')) : fit_platform = "PCH-LP Premium U KBL-R"
						elif any(s in sku_check for s in (' 09 00 00 80 00 ',' 02 B0 02 09 ',' 02 D0 02 09 ')) : fit_platform = "PCH-LP Premium Y KBL-R"
						elif any(s in sku_check for s in (' 02 B0 02 00 ',' 02 D0 02 00 ')) : fit_platform = "PCH-LP Base U SKL" # last, weak pattern
						elif me11_sku_ranges :
							(start_sku_match, end_sku_match) = me11_sku_ranges[-1] # Take last SKU range
							sku_check = krod_fit_sku(start_sku_match) # Store the new SKU check bytes
							me11_sku_ranges.pop(-1) # Remove last SKU range
							continue # Invoke while, check fit_platform in new sku_check
						else : break # Could not find FIT SKU at any KROD
				
				if '-LP' in fit_platform : pos_sku_fit = "LP"
				elif '-H' in fit_platform : pos_sku_fit = "H"
				
				if pos_sku_ext in ['Unknown','Invalid'] : # SKU not retreived from Extension 0C
					if pos_sku_ker == 'Unknown' : # SKU not retreived from Kernel
						if sku == 'NaN' : # SKU not retreived from manual MEA DB entry
							if pos_sku_fit == 'Unknown' : # SKU not retreived from Flash Image Tool
								sku = col_r + 'Error' + col_e + ', unknown ME %s.%s %s SKU!' % (major,minor,sku_init) + col_r + ' *' + col_e
								err_rep += 1
								err_stor.append(sku)
							else :
								sku = sku_init + ' ' + pos_sku_fit # SKU retreived from Flash Image Tool
						else :
							pass # SKU retreived from manual MEA DB entry
					else :
						sku = sku_init + ' ' + pos_sku_ker # SKU retreived from Kernel
				else :
					sku = sku_init + ' ' + pos_sku_ext # SKU retreived from Extension 0C
				
				# Adjust Production PCH Stepping, if not found at DB
				if sku_stp == 'NaN' :
					if (release == 'Production' and (minor == 0 and (hotfix > 0 or (hotfix == 0 and build >= 1158)))) or 20 > minor > 0 :
						if ' LP' in sku : sku_stp = 'C0'
						elif ' H' in sku : sku_stp = 'D0'
				
				# Store SKU and check Latest version for all 11.x
				if sku == "Consumer H" :
					if sku_stp == "NaN" : sku_db = "CON_H_XX"
					else : sku_db = "CON_H" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_CONH' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku == "Consumer LP" :
					if sku_stp == "NaN" : sku_db = "CON_LP_XX"
					else : sku_db = "CON_LP" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_CONLP' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku == "Slim H" :
					if sku_stp == "NaN" : sku_db = "SLM_H_XX"
					else : sku_db = "SLM_H" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_SLMH' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku == "Slim LP" :
					if sku_stp == "NaN" : sku_db = "SLM_LP_XX"
					else : sku_db = "SLM_LP" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_SLMLP' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku == "Corporate H" :
					if sku_stp == "NaN" : sku_db = "COR_H_XX"
					else : sku_db = "COR_H" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_CORH' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				elif sku == "Corporate LP" :
					if sku_stp == "NaN" : sku_db = "COR_LP_XX"
					else : sku_db = "COR_LP" + "_" + sku_stp
					db_maj,db_min,db_hot,db_bld = check_upd(('Latest_ME_11%s_CORLP' % minor))
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
				
				# 11.0 : Skylake, Sunrise Point
				if minor == 0 :
					platform = "SPT"
				
				# 11.5 : Kabylake-LP, Union Point
				elif minor == 5 :
					upd_found = True # Dead branch
					
					platform = "KBP"
				
				# 11.6 : Skylake/Kabylake, Sunrise/Union Point
				elif minor == 6 :
					platform = "SPT/KBP"
				
				# 11.7 : Skylake/Kabylake/Kabylake-R, Sunrise/Union Point
				elif minor == 7 :
					platform = "SPT/KBP"
					
				# 11.10 : Skylake-X/Kabylake-X, Basin Falls
				elif minor == 10 :
					platform = "BSF"
				
				# 11.20 : Skylake-SP, Lewisburg
				elif minor == 20 :
					platform = "LBG"
				
				# 11.x : Unknown
				else :
					sku = col_r + "Error" + col_e + ", unknown ME 11.x Minor version!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
				# Power Down Mitigation (PDM) is an SPT-LP C0 erratum, first fixed at ~11.0.0.1183
				# Hardcoded in FTPR > BUP, cannot detect compression patterns to separate PDM/NOPDM
				# Assumed fixed at KBP-LP A0 but 11.6 has PDM firmware for KBL-upgraded SPT-LP C0
				# 11.0 PDM firmware is tagged accordingly at separate binaries (trustworthy)
				# 11.6-7 PDM firmware tags cannot be trusted, two Kits (SPT/different & KBP/copy)
				# PDM status can be seen at LSB of FW Status Register 3, not trustworthy at 11.6-7
				if ' H' in sku :
					pdm_status = 'NaN'
				else :
					if 'YPDM' in sku_pdm : pdm_status = 'Yes'
					elif 'NPDM' in sku_pdm : pdm_status = 'No'
					elif 'UPDM1' in sku_pdm : pdm_status = 'Unknown 1'
					elif 'UPDM2' in sku_pdm : pdm_status = 'Unknown 2'
					else : pdm_status = 'Unknown'
						
					sku_db += '_%s' % sku_pdm
				
				if ('Error' in sku) or param.me11_sku_disp: me11_sku_anl = True
				
				# Debug SKU detection for all 11.x
				if me11_sku_anl :
					
					err_stor_ker.append(col_m + '\nSKU from Kernel:' + col_e + ' %s' % pos_sku_ker)
					err_stor_ker.append(col_m + 'SKU from Extension 0C:' + col_e + ' %s' % pos_sku_ext)
					err_stor_ker.append(col_m + 'SKU from Flash Image Tool:' + col_e + ' %s' % pos_sku_fit)
					err_stor_ker.append(col_m + 'SKU from ME Analyzer Database:' + col_e + ' %s' % db_sku_chk)
					
					me11_ker_msg = True
					for i in range(len(err_stor_ker)) : err_stor.append(err_stor_ker[i]) # For -msg
				
				# Module Extraction for all x86
				if param.me11_mod_extr :
					x86_unpack(fpt_part_all, fw_type)
					
					continue # Next input file
				
				# UEFIStrip Fix for all 11.x
				if param.extr_mea and sku not in ['Consumer H','Consumer LP','Corporate H','Corporate LP','Slim H','Slim LP'] :
					if sku_init == "Consumer" : sku_db = "CON_X"
					elif sku_init == "Corporate" : sku_db = "COR_X"
					elif sku_init == "Slim" : sku_db = "SLM_X"
			
			# Report unknown ME Major version (AMT 1.x exits before this check)
			elif major < 1 or major > 11 :
				unk_major = True
				sku = col_r + "Error" + col_e + ", unknown ME SKU due to unknown Major version!" + col_r + " *" + col_e
				err_rep += 1
				err_stor.append(sku)
		
		elif variant == "TXE" : # Trusted Execution Engine (SEC)
		
			if sku_match is not None :
				sku_txe = reading[start_sku_match + 8:start_sku_match + 0x10]
				sku_txe = binascii.b2a_hex(sku_txe).decode('utf-8').upper() # Hex value with Little Endianess
			
			if major == 1 or major == 0 :
				if rsa_pkey == "C7E5538622F3A6EC90F5F7CCD76FA8F1" or rsa_pkey == "5FB2D04BC4D8B4E90AECB5C708458F95" :
					txe_sub = " M/D"
					txe_sub_db = "_MD"
				elif rsa_pkey == "FF9F0A456C6D120D1C021E4453E5F726" : # Unknown I/T Pre-Production RSA Public Key
					txe_sub = " I/T"
					txe_sub_db = "_IT"
				else :
					txe_sub = " UNK"
					txe_sub_db = "_UNK_RSAPK_" + rsa_pkey # Additionally prints the unknown RSA Public Key
					err_rep += 1
				
				if major == 0 : # Weird TXE 1.0/1.1 (3MB/1.375MB) Android-only testing firmware (Rom_8MB_Tablet_Android, Teclast X98 3G)
					# PSI fiwi version 06 for BYT board Android_BYT_B0_Engg_IFWI_00.14 (from flash batch script)
					if sku_txe == "675CFF0D06430000" : # xxxxxxxx06xxxxxx is ~3MB for TXE v0.x
						sku = "3MB" + txe_sub
						sku_db = "3MB" + txe_sub_db
					else :
						sku = col_r + "Error" + col_e + ", unknown TXE 0.x SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
				
				elif major == 1 :
					if minor == 0 :
						if sku_txe == "675CFF0D03430000" : # xxxxxxxx03xxxxxx is 1.25MB for TXE v1.0
							sku = "1.25MB" + txe_sub
							sku_db = "1.25MB" + txe_sub_db
							if txe_sub_db == "_MD" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_10_125MB_MD')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
							elif txe_sub_db == "_IT" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_10_125MB_IT')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
						elif sku_txe == "675CFF0D05430000" : # xxxxxxxx05xxxxxx is 3MB for TXE v1.0
							sku = "3MB" + txe_sub
							sku_db = "3MB" + txe_sub_db
							if txe_sub_db == "_MD" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_10_3MB_MD')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
							elif txe_sub_db == "_IT" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_10_3MB_IT')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
						else :
							sku = col_r + "Error" + col_e + ", unknown TXE 1.0 SKU!" + col_r + " *" + col_e
							err_rep += 1
							err_stor.append(sku)
					elif minor == 1 :
						if sku_txe == "675CFF0D03430000" : # xxxxxxxx03xxxxxx is 1.375MB for TXE v1.1 (same as 1.25MB TXE v1.0)
							sku = "1.375MB" + txe_sub
							sku_db = "1.375MB" + txe_sub_db
							if txe_sub_db == "_MD" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_11_1375MB_MD')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
							elif txe_sub_db == "_IT" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_11_1375MB_IT')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
						else :
							sku = col_r + "Error" + col_e + ", unknown TXE 1.1 SKU!" + col_r + " *" + col_e
							err_rep += 1
							err_stor.append(sku)
					elif minor == 2 :
						if sku_txe == "675CFF0D03430000" : # xxxxxxxx03xxxxxx is 1.375MB for TXE v1.2 (same as v1.0 1.25MB and v1.1 1.375MB)
							sku = "1.375MB" + txe_sub
							sku_db = "1.375MB" + txe_sub_db
							if txe_sub_db == "_MD" :
								db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_12_1375MB_MD')
								if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
							#elif txe_sub_db == "_IT" :
								#db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_12_1375MB_IT')
								#if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
						else :
							sku = col_r + "Error" + col_e + ", unknown TXE 1.2 SKU!" + col_r + " *" + col_e
							err_rep += 1
							err_stor.append(sku)
					else :
						sku = col_r + "Error" + col_e + ", unknown TXE 1.x Minor version!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
					
					platform = "Bay Trail"
					
			elif major == 2 :
				if rsa_pkey == "87FF93E922C97926248C139DC902292A" or rsa_pkey == "5FB2D04BC4D8B4E90AECB5C708458F95" :
					txe_sub = " BSW/CHT"
					txe_sub_db = "_BSW-CHT"
				else :
					txe_sub = " UNK"
					txe_sub_db = "_UNK_RSAPK_" + rsa_pkey # Additionally prints the unknown RSA Public Key
					err_rep += 1
				
				if minor == 0 :
					if sku_txe == "675CFF0D03430000" :
						if 'UNK' in txe_sub : sku = "1.375MB" + txe_sub
						else : sku = sku = "1.375MB" # No need for + txe_sub as long as there is only one platform
						if 'UNK' in txe_sub_db : sku_db = "1.375MB" + txe_sub_db
						else : sku_db = "1.375MB" # No need for + txe_sub_db as long as there is only one platform
						if txe_sub_db == "_BSW-CHT" :
							db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_20_1375MB')
							if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					else :
						sku = col_r + "Error" + col_e + ", unknown TXE 2.0 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
				elif minor == 1 :
					if sku_txe == "675CFF0D03430000" :
						if 'UNK' in txe_sub : sku = "1.375MB" + txe_sub
						else : sku = sku = "1.375MB" # No need for + txe_sub as long as there is only one platform
						if 'UNK' in txe_sub_db : sku_db = "1.375MB" + txe_sub_db
						else : sku_db = "1.375MB" # No need for + txe_sub_db as long as there is only one platform
						if txe_sub_db == "_BSW-CHT" :
							db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_21_1375MB')
							if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					else :
						sku = col_r + "Error" + col_e + ", unknown TXE 2.1 SKU!" + col_r + " *" + col_e
						err_rep += 1
						err_stor.append(sku)
				else :
					sku = col_r + "Error" + col_e + ", unknown TXE 2.x Minor version!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
				
				platform = "BSW/CHT"
				
			elif major == 3 :
				cpd_offset,cpd_mod_attr,cpd_ext_attr,vcn,fw_0C_sku1,fw_0C_lbg,fw_0C_sku2 = ext_anl('$MN2', start_man_match) # Detect x86 Attributes
				
				sku_check,me11_sku_ranges = krod_anl() # Detect FIT SKU
				
				# TXE3 PRD & PRE in IFWI/BIOS, BYP in TXE Region
				if fw_type == 'Update' : fw_type = "Region, Extracted"
				
				db_sku_chk,sku,sku_stp,sku_pdm = db_skl(variant) # Retreive SKU & Rev from DB
				
				# Simultaneous branches
				if minor in [0,2] : # 2 is "Slim" ???
					db_maj,db_min,db_hot,db_bld = check_upd('Latest_TXE_3%s' % minor)
					if hotfix < db_hot or (hotfix == db_hot and build < db_bld) : upd_found = True
					
					# Adjust SoC Stepping if not from DB
					if minor == 0 and sku_stp == "NaN" :
						if release == "Production" : sku_stp = 'Bx' # PRD
						else : sku_stp = 'Ax' # PRE, BYP
					elif minor == 2 and sku_stp == "NaN" :
						if release == "Production" : sku_stp = 'Cx' # PRD (Joule_C0-X64-Release)
				
				else :
					sku = col_r + "Error" + col_e + ", unknown TXE 3.x Minor version!" + col_r + " *" + col_e
					err_rep += 1
					err_stor.append(sku)
					
				# Single/No SKU for TXE3, Rev only
				if sku_stp == "NaN" : sku_db = "XX"
				else : sku_db = sku_stp
				
				# Module Extraction for all x86
				if param.me11_mod_extr :
					x86_unpack(fpt_part_all, fw_type)
					
					continue # Next input file
				
				platform = "Apollo Lake"
			
			elif major > 3 :
				unk_major = True
				sku = col_r + "Error" + col_e + ", unknown TXE SKU due to unknown Major version" + col_r + " *" + col_e
				err_rep += 1
				err_stor.append(sku)
				
		elif variant == 'SPS' :
			
			if sku_match is not None :
				sku_sps = reading[start_sku_match + 8:start_sku_match + 0xC]
				sku_sps = binascii.b2a_hex(sku_sps).decode('utf-8').upper() # Hex value with Little Endianess
			
			opr2_pat = re.compile(br'\x4F\x50\x52\x32\xFF\xFF\xFF\xFF') # OPR2 detection for SPS2,3,4 (the 4xFF force FPT area only)
			opr2_match = opr2_pat.search(reading)
			
			cod2_pat = re.compile(br'\x43\x4F\x44\x32\xFF\xFF\xFF\xFF') # COD2 detection for SPS1 (the 4xFF force FPT area only)
			cod2_match = cod2_pat.search(reading)
			
			if not rgn_exist :
				# REC detection always first, FTPR Manifest
				if major == 1 :
					sps1_rec_pat = re.compile(br'\x45\x70\x73\x52\x65\x63\x6F\x76\x65\x72\x79') # EpsRecovery detection
					sps1_rec_match = sps1_rec_pat.search(reading)
					if sps1_rec_match is not None : fw_type = "Recovery"
					else : fw_type = "Operational"
				elif major < 4 :
					mme_pat = re.compile(br'\x24\x4D\x4D\x45') # $MME detection
					mme_match = mme_pat.findall(reading)
					if len(mme_match) == 1 : fw_type = "Recovery" # SPSRecovery , FTPR for SPS2,3 (only $MMEBUP section)
					elif len(mme_match) > 1 : fw_type = "Operational" # SPSOperational , OPR1/OPR2 for SPS2,3 or COD1/COD2 for SPS1 regions
				else :
					norgn_sps_match = (re.compile(br'\x24\x43\x50\x44.\x00\x00\x00\x01\x01\x10.\x46\x54\x50\x52', re.DOTALL)).search(reading) # SPSRecovery, $CPD + [0x8] + FTPR
					if norgn_sps_match is not None : fw_type = "Recovery"
					else :
						norgn_sps_match = (re.compile(br'\x24\x43\x50\x44.\x00\x00\x00\x01\x01\x10.\x4F\x50\x52\x00', re.DOTALL)).search(reading) # SPSOperational, $CPD + [0x8] + OPR.
						if norgn_sps_match is not None : fw_type = "Operational"
			else :
				if opr2_match is not None or cod2_match is not None :
					sub_sku = "1" # xx.xx.xxx.1
					opr_mode = "Dual OPR"
				else :
					sub_sku = "0" # xx.xx.xxx.0
					opr_mode = "Single OPR"
			
			if major == 3 and rgn_exist :
				nm_sien_match = (re.compile(br'\x4F\x75\x74\x6C\x65\x74\x20\x54\x65\x6D\x70')).search(reading) # "Outlet Temp" detection (NM only)
				if nm_sien_match is not None : sps_serv = "Node Manager" # NM
				else : sps_serv = "Silicon Enabling" # SiEn
				
			elif major == 4 :
				cpd_offset,cpd_mod_attr,cpd_ext_attr,vcn,fw_0C_sku1,fw_0C_lbg,fw_0C_sku2 = ext_anl('$MN2', start_man_match) # Detect x86 Attributes
			
				if param.me11_mod_extr :
					# Module Extraction for all x86
					x86_unpack(fpt_part_all, fw_type)
					
					continue # Next input file
		
		# Partial Firmware Update Detection (WCOD, LOCL)
		locl_start = (re.compile(br'\x24\x43\x50\x44.\x00\x00\x00\x01\x01\x10.\x4C\x4F\x43\x4C', re.DOTALL)).search(reading[:0x10])
		if (variant == "ME") and (major == 11) and (locl_start is not None) :
			if locl_start.start() == 0 : # Partial Update has "$CPD + [0x8] + LOCL" at first 0x10
				wcod_found = True
				fw_type = "Partial Update"
				sku = "Corporate"
				del err_stor[:]
				err_rep = 0
		elif (variant == "ME") and (major < 11) and (sku_match is None) : # Partial Updates do not have $SKU
			wcod_match = (re.compile(br'\x24\x4D\x4D\x45\x57\x43\x4F\x44')).search(reading) # $MMEWCOD detection (found at 5MB & Partial Update firmware)
			if wcod_match is not None :
				wcod_found = True
				fw_type = "Partial Update"
				sku = "5MB"
				del err_stor[:]
				err_rep = 0
		
		# ME Firmware non Partial Update without $SKU
		if sku_match is None and fw_type != "Partial Update" and not me_rec_ffs :
			if (variant == "ME" and 1 < major < 11) or (variant == "TXE" and major < 3) or (variant == "SPS" and major < 4) :
				sku_missing = True
				err_rep += 1
		
		# Create Firmware Type DB entry
		fw_type, type_db = fw_types(fw_type)
		
		# Create firmware DB names
		if variant == "ME" or variant == "TXE" :
			name_db = "%s.%s.%s.%s_%s_%s_%s" % (major, minor, hotfix, build, sku_db, rel_db, type_db) # The re-created filename without extension
			name_db_rgn = "%s.%s.%s.%s_%s_%s_RGN_%s" % (major, minor, hotfix, build, sku_db, rel_db, rsa_hash) # The equivalent "clean" RGN filename
			name_db_extr = "%s.%s.%s.%s_%s_%s_EXTR_%s" % (major, minor, hotfix, build, sku_db, rel_db, rsa_hash) # The equivalent "dirty" EXTR filename
		elif variant == "SPS" :
			if sub_sku == "NaN" :
				name_db = "%s.%s.%s.%s_%s_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), rel_db, type_db)
				name_db_rgn = "%s.%s.%s.%s_%s_RGN_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), rel_db, rsa_hash) # The equivalent RGN filename
				name_db_extr = "%s.%s.%s.%s_%s_EXTR_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), rel_db, rsa_hash) # The equivalent EXTR filename
				name_db_0_extr = "%s.%s.%s.%s.0_%s_EXTR_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), rel_db, rsa_hash) # The equivalent EXTR 0 filename
				name_db_1_extr = "%s.%s.%s.%s.1_%s_EXTR_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), rel_db, rsa_hash) # The equivalent EXTR 1 filename
			else :
				name_db = "%s.%s.%s.%s.%s_%s_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), sub_sku, rel_db, type_db)
				name_db_rgn = "%s.%s.%s.%s.%s_%s_RGN_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), sub_sku, rel_db, rsa_hash) # The equivalent RGN filename
				name_db_extr = "%s.%s.%s.%s.%s_%s_EXTR_%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), sub_sku, rel_db, rsa_hash) # The equivalent EXTR filename
		
		name_db_hash = name_db + '_' + rsa_hash
		
		if param.db_print_new :
			with open(mea_dir + os_dir + 'MEA_DB_NEW.txt', 'a') as db_file : db_file.write(name_db_hash + '\n')
			continue # Next input file
		
		# Search firmware database, all firmware filenames have this stucture: Major.Minor.Hotfix.Build_SKU_Release_Type
		fw_db = db_open()
		if not wcod_found and not me_rec_ffs : # Must not be Partial Update or MERecovery
			if (((variant == "ME" or variant == "TXE") and sku_db != "NaN") or err_sps_sku == "") and rel_db != "NaN" and type_db != "NaN" : # Search database only if SKU, Release & Type are known
				for line in fw_db :
					if len(line) < 2 or line[:3] == "***" :
						continue # Skip empty lines or comments
					else : # Search the re-created file name without extension at the database
						if name_db_hash in line : fw_in_db_found = "Yes" # Known firmware, nothing new
						if type_db == "EXTR" and name_db_rgn in line :
							rgn_over_extr_found = True # Same firmware found at database but RGN instead of imported EXTR, so nothing new
							fw_in_db_found = "Yes"
						if type_db == "UPD" and ((variant == "ME" and (major > 7 or (major == 7 and release != "Production") or
							(major == 6 and sku == "Ignition"))) or variant == "TXE") : # Only for ME8 and up or ME7 non-PRD or ME6.0 IGN
							# noinspection PyUnboundLocalVariable
							if (name_db_rgn in line) or (name_db_extr in line) : rgn_over_extr_found = True # Same RGN/EXTR firmware found at database, UPD disregarded
						# noinspection PyUnboundLocalVariable
						if (type_db == "OPR" or type_db == "REC") and ((name_db_0_extr in line) or (name_db_1_extr in line)) : rgn_over_extr_found = True # Same EXTR found at DB, OPR/REC disregarded
				fw_db.close()
			# If SKU and/or Release and/or Type are NaN (unknown), the database will not be searched but rare firmware will be reported (Partial Update excluded)
		else :
			can_search_db = False # Do not search DB for Partial Update images
		
		# Check if firmware is updated, Production only
		if release == "Production" and err_rep == 0 and not wcod_found : # Does not display if there is any error or firmware is Partial Update
			if variant == "TXE" and major == 0 : pass # Exclude TXE v0.x
			elif variant in ['ME','TXE'] : # SPS excluded
				if upd_found : upd_rslt = "Latest:   " + col_r + "No" + col_e
				elif not upd_found : upd_rslt = "Latest:   " + col_g + "Yes" + col_e
		
		# Rename input file based on the DB structured name
		if param.give_db_name :
			file_name = file_in
			new_dir_name = os.path.join(os.path.dirname(file_in), name_db + '.bin')
			f.close()
			if not os.path.exists(new_dir_name) : os.rename(file_name, new_dir_name)
			elif os.path.basename(file_in) == name_db + '.bin' : pass
			else : print(col_r + 'Error: ' + col_e + 'A file with the same name already exists!')
			
			continue # Next input file
		
		# UEFI Bios Updater Pre-Menu Integration (must be after processing but before message printing)
		if param.ubu_mea_pre :
			if can_search_db and not rgn_over_extr_found and fw_in_db_found == "No" :
				print(col_y + "Engine firmware not found at the database, run ME Analyzer for details!" + col_e)
			mea_exit(9)
		
		# UEFI Strip Integration (must be after Printed Messages)
		elif param.extr_mea :
			if fw_in_db_found == "No" and not rgn_over_extr_found and not wcod_found : 
				# noinspection PyUnboundLocalVariable
				if variant == 'ME' and major == 11 and (sku_db == 'CON_X' or sku_db == 'COR_X') and sku_stp == 'NaN' and sku_pdm == 'NaN' : sku_db += "_XX_UPDM"
				if variant != 'SPS' : name_db = "%s_%s_%s_%s_%s" % (fw_ver(major,minor,hotfix,build), sku_db, rel_db, type_db, rsa_hash)
				else : name_db = "%s_%s_%s_%s" % (fw_ver(major,minor,hotfix,build), rel_db, type_db, rsa_hash) # No SKU for SPS
				
			if fuj_rgn_exist : name_db = "%s_UMEM" % name_db
			
			if me_rec_ffs : print("%s %s_NaN_REC %s NaN %s" % (variant, fw_ver(major,minor,hotfix,build), fw_ver(major,minor,hotfix,build), date))
			else : print("%s %s %s %s %s" % (variant, name_db, fw_ver(major,minor,hotfix,build), sku_db, date))
			
			mea_exit(0)
		
		# Print MEA Messages
		elif variant == "SPS" and not param.print_msg :
			print("Family:   %s" % variant)
			if sub_sku != "NaN" : print("Version:  %s.%s.%s.%s.%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build), sub_sku)) # xx.xx.xx.xxx.y
			else : print("Version:  %s.%s.%s.%s" % ("{0:02d}".format(major), "{0:02d}".format(minor), "{0:02d}".format(hotfix), "{0:03d}".format(build))) # xx.xx.xx.xxx
			print("Release:  %s" % release)
			if sps_serv != "NaN" : print("Service:  %s" % sps_serv)
			print("Type:     %s" % fw_type)
			if opr_mode != "NaN" : print("Mode:     %s" % opr_mode)
			if major == 4 : # Only for x86
				print("SVN:      %s" % svn)
				print("VCN:      %s" % vcn)
			print("Date:     %s" % date)
			if fitc_ver_found : print("FIT Ver:  %s" % fw_ver(fitc_major,fitc_minor,fitc_hotfix,fitc_build))
			if rgn_exist : print('Size:     0x%X' % eng_fw_end)
			print("\nIntel SPS firmware is not officially supported")
		elif not param.print_msg :
			print("Family:   %s" % variant)
			print("Version:  %s.%s.%s.%s" % (major, minor, hotfix, build))
			print("Release:  %s" % release)
			
			if not me_rec_ffs : # The following should not appear when ME-REC modules are loaded
				
				print("Type:     %s" % fw_type)

				if fd_lock_state == 2 : print("FD:       Unlocked")
				elif fd_lock_state == 1 : print("FD:       Locked")
				
				if (variant == "TXE" and major > 2 and 'Error' not in sku) or wcod_found : pass
				else : print("SKU:      %s" % sku)

				if (variant == "ME" and major >= 11) or (variant == "TXE" and major >= 3):
					if sku_stp != "NaN" : print("Rev:      %s" % sku_stp)
					elif wcod_found : pass
					else : print("Rev:      Unknown")
				
				if ((variant == "ME" and major >= 8) or variant == "TXE") and not wcod_found :
					print("SVN:      %s" % svn)
					print("VCN:      %s" % vcn)
				
				# noinspection PyUnboundLocalVariable
				if [variant,major,wcod_found] == ['ME',11,False] :
					if pdm_status != 'NaN' : print("PDM:      %s" % pdm_status)
					# noinspection PyUnboundLocalVariable
					print("LBG:      %s" % lbg_support)
				
				if pvpc != "NaN" and wcod_found is False : print("PV:       %s" % pvpc)
				
				print("Date:     %s" % date)
				
				if ((variant == "ME" and major <= 10) or variant == "TXE") and fitc_ver_found:
					print("FITC Ver: %s" % fw_ver(fitc_major,fitc_minor,fitc_hotfix,fitc_build))
				elif variant == "ME" and major > 10 and fitc_ver_found:
					print("FIT Ver:  %s" % fw_ver(fitc_major,fitc_minor,fitc_hotfix,fitc_build))
				
				if fit_platform != "NaN" :
					if variant == "ME" and major == 11 : print("FIT SKU:  %s" % fit_platform)
				
				if rgn_exist :
					if major ==6 and release == "ROM-Bypass" : print('Size:     Unknown')
					else : print('Size:     0x%X' % eng_fw_end)
				
				if platform != "NaN" : print("Platform: %s" % platform)
				
				if upd_rslt != "" : print(upd_rslt)
				
				# Display ME7 Blacklist
				if major == 7 :
					print("")
					if me7_blist_1_build != 0 :
						# noinspection PyUnboundLocalVariable
						print("Blist 1:  <= 7.%s.%s.%s" % (me7_blist_1_minor, me7_blist_1_hotfix, me7_blist_1_build))
					else :
						print("Blist 1:  Empty")
					if me7_blist_2_build != 0 :
						# noinspection PyUnboundLocalVariable
						print("Blist 2:  <= 7.%s.%s.%s" % (me7_blist_2_minor, me7_blist_2_hotfix, me7_blist_2_build))
					else :
						print("Blist 2:  Empty")
			elif me_rec_ffs :
				err_rep = 0
				del err_stor[:]
				print("Date:     %s" % date)
				print("GUID:     821D110C-D0A3-4CF7-AEF3-E28088491704")
				
		# General MEA Messages (must be Errors > Warnings > Notes)
		if unk_major : gen_msg(err_stor, col_r + "Error: unknown Intel Engine Major version! *" + col_e, '')
		
		if not param.print_msg and me11_ker_msg and fw_type != "Partial Update" :
			for i in range(len(err_stor_ker)) : print(err_stor_ker[i])
		
		if rec_missing and fw_type != "Partial Update" : gen_msg(err_stor, col_r + "Error: Recovery section missing, Manifest Header not found! *" + col_e, '')
		
		# noinspection PyUnboundLocalVariable
		if not man_valid[0] : gen_msg(err_stor, col_r + "Error: Invalid FTPR RSA Signature! *" + col_e, '')
		
		if sku_missing : gen_msg(err_stor, col_r + "Error: SKU tag missing, incomplete Intel Engine firmware!" + col_e, '')
		
		if variant == "TXE" and ('UNK' in txe_sub) : gen_msg(err_stor, col_r + "Error: Unknown TXE %s.x platform! *" % major + col_e, '')
		
		if uf_error : gen_msg(err_stor, col_r + 'Error: UEFIFind Engine GUID detection failed!' + col_e, '')
		
		if err_rep > 0 : gen_msg(err_stor, col_r + "* Please report this issue!" + col_e, '')
		
		if eng_size_text != '' : gen_msg(warn_stor, col_m + '%s' % eng_size_text + col_e, '')
		
		if fpt_chk_fail : gen_msg(warn_stor, col_m + "Warning: Wrong $FPT checksum %s, expected %s!" % (fpt_chk_file,fpt_chk_calc) + col_e, '')
		
		if sps3_chk_fail : gen_msg(warn_stor, col_m + "Warning: Wrong $FPT SPS3 checksum %s, expected %s!" % (sps3_chk16_file,sps3_chk16_calc) + col_e, '')
		
		if fpt_num_fail : gen_msg(warn_stor, col_m + "Warning: Wrong $FPT entry count %s, expected %s!" % (fpt_num_file,fpt_num_calc) + col_e, '')
		
		if fuj_rgn_exist : gen_msg(warn_stor, col_m + "Warning: Fujitsu Intel Engine firmware detected!" + col_e, '')
		
		if me_rec_ffs : gen_msg(warn_stor, col_m + "Warning: This is not a valid Intel Engine firmware image!" + col_e, 'del')
				
		if multi_rgn : gen_msg(note_stor, col_y + "Note: Multiple (%d) Intel Engine firmware detected in file!" % fpt_count + col_e, '')
		
		if can_search_db and not rgn_over_extr_found and fw_in_db_found == "No" : gen_msg(note_stor, col_g + "Note: This firmware was not found at the database, please report it!" + col_e, '')
		
		if found_guid != "" : gen_msg(note_stor, col_y + 'Note: Detected Engine GUID %s!' % found_guid + col_e, '')
		
		# Print Error/Warning/Note Messages
		if param.print_msg : msg_rep()
		
		if param.ubu_mea : print()
		
		if param.multi : multi_drop()
		
		f.close()
		
	if param.help_scr : mea_exit(0) # Only once for -?
	
mea_exit(0)