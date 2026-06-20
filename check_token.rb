token = Token.where(name: "agent-full-access-v2").first
if token
  perms = token.preferences["permission"] || []
  puts "Token: #{token.name}"
  puts "Permissions count: #{perms.length}"
  puts "Has 'admin': #{perms.include?('admin')}"
  puts "Has 'ticket.agent': #{perms.include?('ticket.agent')}"
  puts "Has 'user_preferences': #{perms.include?('user_preferences')}"
  puts ""
  puts "All permissions:"
  puts perms.sort.join(", ")
else
  puts "Token not found"
  Token.all.each { |t| puts "  #{t.name} (user_id: #{t.user_id})" }
end
