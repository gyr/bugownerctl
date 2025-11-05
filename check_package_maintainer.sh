#!/usr/bin/env sh

FILE="_maintainership.json"
WHITELIST_FILE="whitelist_maintainership.json"
PACKAGE=$1

if jq -e '."'"$PACKAGE"'"' "$FILE" > /dev/null; then
  echo "Package '$PACKAGE' is present in $FILE."
else
    echo "Package '$PACKAGE' is NOT present in $FILE."
    if jq -e '.[] | select(. == "'"$PACKAGE"'")' "$WHITELIST_FILE" > /dev/null; then
        echo "Package '$PACKAGE' is present in the $WHITELIST_FILE."
    else
        echo "Package '$PACKAGE' is NOT present in the $WHITELIST_FILE."
        exit 1
    fi
fi
