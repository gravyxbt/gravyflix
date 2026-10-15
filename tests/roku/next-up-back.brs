sub Main()
    m.top = {dismissed:0,releasedFocus:0,activated:0}
    m.okHeld = false
    check(onKeyEvent("back",true), "Countdown Back is consumed by overlay")
    check(m.top.dismissed = 1 and m.top.activated = 0, "First Back dismisses without starting another title")
    check(not onKeyEvent("back",false), "Back release does not dismiss twice")
    check(m.top.dismissed = 1, "Dismiss happens once")
    print "PASS: Next-up Back dismissal"
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
