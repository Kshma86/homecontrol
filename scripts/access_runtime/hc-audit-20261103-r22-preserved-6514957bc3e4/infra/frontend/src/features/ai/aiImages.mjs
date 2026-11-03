export function validateImageFiles(files, existingCount = 0) {
  if (existingCount + files.length > 4) throw new Error("Legfeljebb 4 kép csatolható.");
  for (const file of files) {
    if (!/\.(jpe?g|png|webp)$/i.test(file.name) || !["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Csak JPG, PNG vagy WebP kép csatolható.");
    if (!file.size || file.size > 3 * 1024 * 1024) throw new Error("Egy kép legfeljebb 3 MiB méretű lehet.");
  }
}

export function storedAiMessages(messages, limit) {
  return messages.map(({ typing, fullContent, images, ...message }) => ({
    ...message,
    content: fullContent || message.content,
  })).slice(-limit);
}

export function imagePayload(images) {
  return images.map(({ mime_type, data }) => ({ mime_type, data }));
}
