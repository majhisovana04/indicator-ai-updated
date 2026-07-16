# app/loaders/block_splitter.py

class BlockSplitter:
    """
    Shared utility for splitting markdown content into blocks
    using '---' as the separator. Used by FAQLoader and PolicyLoader.
    """

    @staticmethod
    def split_blocks(content: str) -> list[str]:
        return [
            block.strip()
            for block in content.split("---")
            if block.strip()
        ]