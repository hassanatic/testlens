*** Settings ***
Documentation     Acceptance checks for the framed serial protocol.
Library           FramingLibrary.py

*** Test Cases ***
Frames Arrive In Order
    Send Frame    temp=21.5
    Send Frame    temp=21.6
    Received Frames Should Be    temp=21.5    temp=21.6

Line Noise Before A Frame Is Ignored
    Send Raw Bytes    00ff11
    Send Frame    ok
    Received Frames Should Be    ok

Corrupted Frame Is Counted And Skipped
    Send Corrupted Frame    broken
    Send Frame    next
    Received Frames Should Be    next
    Crc Error Count Should Be    1
