sub init()
    m.highlight = m.top.FindNode("highlight")
    m.index = 0
    m.tabs = ["home", "movies", "shows", "search"]
    m.selectedLine = m.top.FindNode("selectedLine")
    onSelectedTab()
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
        if m.index < m.tabs.Count() - 1 then m.index++
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

sub onSelectedTab()
    if m.tabs = invalid or m.selectedLine = invalid then return
    for i = 0 to m.tabs.Count() - 1
        label = m.top.FindNode(m.tabs[i])
        label.color = "0xB8C2D1FF"
        if m.tabs[i] = m.top.selectedTab
            m.index = i
            label.color = "0xFFFFFFFF"
            m.selectedLine.translation = [29 + i * 132, 43]
        end if
    end for
    onFocus()
end sub
