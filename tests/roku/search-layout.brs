sub Main()
    for each bounds in [{x:0,y:0,width:400,height:480},{x:0,y:0,width:600,height:520},{x:-8,y:-4,width:650,height:800}]
        layout = SearchKeyboardPlacement(bounds)
        bottom = 200 + layout.translation[1] + (bounds.y + bounds.height) * layout.scale
        right = 64 + layout.translation[0] + (bounds.x + bounds.width) * layout.scale
        check(bottom <= 584.01, "Keyboard fits above the action row")
        check(612 - bottom >= 27.99, "Native bottom row has at least 28 pixels of separation")
        check(right <= 512.01, "Keyboard fits the left pane")
        check(layout.scale <= 0.82, "Small keyboards are not over-enlarged")
    end for
    check(SearchKeyboardPlacement({width:0,height:0}) = invalid, "Unconstructed widgets are retried safely")
    check(SearchKeyboardPlacement(invalid) = invalid, "Missing bounds do not divide by zero")
    print "PASS: Search keyboard layout"
end sub
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
