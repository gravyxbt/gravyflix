sub init()
    m.highlight = m.top.FindNode("highlight")
    m.index = 0
    m.tabs = ["home", "movies", "search"]
    m.top.ObserveField("focusedChild", "onFocus")
end sub

sub onFocus()
    m.highlight.visible = m.top.HasFocus()
    m.highlight.translation = [m.index * 132, 0]
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "left"
        if m.index > 0 then m.index--
    else if key = "right"
        if m.index < 2 then m.index++
    else if key = "down"
        m.top.exitDown++
    else if key = "OK"
        m.top.activated = m.tabs[m.index]
    else
        return false
    end if
    onFocus()
    return true
end function
