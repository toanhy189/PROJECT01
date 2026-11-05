// 1. Tổng quan các phát biểu trong snapshot; một fact có thể có nhiều evidence.
MATCH p=(s:Entity)<-[:SUBJECT]-(f:RelationFact)-[:OBJECT]->(o:Entity)
WHERE f.snapshot_id=$sid
RETURN p LIMIT 40;

// 2. Nhóm thực thể liên quan diabetes, không tự tạo quan hệ còn thiếu.
MATCH p=(s:Entity {snapshot_id:$sid, entity_id:'diabetes'})
        <-[:SUBJECT]-(f:RelationFact)-[:OBJECT]->(o:Entity)
WHERE f.snapshot_id=$sid
RETURN p LIMIT 25;

// 3. Các quan hệ của thực thể do người demo chọn bằng $entity_id.
MATCH p=(s:Entity {snapshot_id:$sid, entity_id:$entity_id})
        <-[:SUBJECT|OBJECT]-(f:RelationFact)-[:SUBJECT|OBJECT]->(o:Entity)
WHERE f.snapshot_id=$sid AND o<>s
RETURN p LIMIT 25;

// 4. Evidence riêng của một phát biểu, có thể click để xem quote/checked_by/status.
MATCH p=(f:RelationFact {snapshot_id:$sid, relation_id:$relation_id})
        -[:SUPPORTED_BY]->(e:Evidence)-[:FROM_CHUNK]->(c:Chunk)
RETURN p LIMIT 20;

// 5. Đường liên kết đầy đủ tới tài liệu gốc chứa URL.
MATCH p=(f:RelationFact {snapshot_id:$sid, relation_id:$relation_id})
        -[:SUPPORTED_BY]->(e:Evidence)-[:FROM_CHUNK]->(c:Chunk)-[:FROM_DOCUMENT]->(d:Document)
RETURN p LIMIT 20;

// 6. Hai bước quan hệ y khoa tương ứng hai RelationFact, không suy diễn nhân quả.
MATCH p=(s:Entity {snapshot_id:$sid, entity_id:'prediabetes'})
        <-[:SUBJECT|OBJECT]-(f1:RelationFact)-[:SUBJECT|OBJECT]->(m:Entity)
        <-[:SUBJECT|OBJECT]-(f2:RelationFact)-[:SUBJECT|OBJECT]->(last:Entity)
WHERE f1.snapshot_id=$sid AND f2.snapshot_id=$sid AND f1<>f2
  AND s<>m AND s<>last AND m<>last
RETURN p LIMIT 20;
