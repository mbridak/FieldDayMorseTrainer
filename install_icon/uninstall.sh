#!/bin/bash

if [ -f "~/.local/bin/FieldDayMorseTrainer" ]; then
	rm ~/local/bin/FieldDayMorseTrainer
fi

xdg-icon-resource uninstall --size 64 k6gte-FieldDayMorseTrainer

xdg-desktop-icon uninstall k6gte-FieldDayMorseTrainer.desktop

xdg-desktop-menu uninstall k6gte-FieldDayMorseTrainer.desktop

