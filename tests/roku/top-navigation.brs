sub Main()
    m.tabs = ["home", "movies", "shows", "search"]
    m.index = 0
    m.highlight = {}
    m.top = {HasFocus:hasFocus}
    check(onKeyEvent("right", true), "Navigate to Movies")
    check(onKeyEvent("right", true), "Navigate to Shows")
    check(onKeyEvent("OK", true) and m.top.activated = "shows", "OK activates Shows")
    onKeyEvent("right", true)
    onKeyEvent("right", true)
    check(m.index = 3, "Right stops at Search")
    onKeyEvent("left", true)
    check(m.index = 2, "Left returns to Shows")
    check(not onKeyEvent("back", true), "Back bubbles out of navigation")
    print "PASS: Top navigation"
end sub
function hasFocus() as boolean
    return true
end function
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
