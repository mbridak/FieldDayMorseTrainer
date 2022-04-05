#!/bin/bash

if [ -f "../dist/FieldDayMorseTrainer" ]; then
	cp ../dist/FieldDayMorseTrainer ~/.local/bin/
fi

xdg-icon-resource install --size 64 --context apps --mode user k6gte-FieldDayMorseTrainer.png k6gte-FieldDayMorseTrainer

xdg-desktop-icon install k6gte-FieldDayMorseTrainer.desktop

xdg-desktop-menu install k6gte-FieldDayMorseTrainer.desktop

